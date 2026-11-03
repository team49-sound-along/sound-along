from __future__ import annotations

from aws_cdk import Duration
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

LAMBDA_RETRY_ERRORS: tuple[str, ...] = (
    "Lambda.ServiceException",
    "Lambda.AWSLambdaException",
    "Lambda.SdkClientException",
    # Reserved concurrency is only 2, so throttling is an expected transient error.
    "Lambda.TooManyRequestsException",
)


def create_state_machine(scope: Construct, generator: lambda_.IFunction, questions: lambda_.IFunction | None = None) -> sfn.StateMachine:
    """generator -> (only if it reported done) -> questions for ENGLISH passages -> translation. Questions and translation are best effort: each has
    its own Catch, so neither can ever fail an audio job, and only a throttled translation is retried (twice)."""
    invoke = tasks.LambdaInvoke(
        scope,
        "InvokeGenerator",
        lambda_function=generator,
        # Default payload is the whole execution input; unwrap the Lambda response envelope.
        output_path="$.Payload",
        retry_on_service_exceptions=False,
    ).add_retry(errors=list(LAMBDA_RETRY_ERRORS), max_attempts=1, interval=Duration.seconds(5))

    # Translation: the same generator image in translate mode, a SECOND invocation (own 15-minute budget, own failure).
    translate = tasks.LambdaInvoke(
        scope,
        "InvokeTranslation",
        lambda_function=generator,
        payload=sfn.TaskInput.from_object(
            {"mode": "translate", "jobId": sfn.JsonPath.string_at("$.jobId"), "passageId": sfn.JsonPath.string_at("$.passageId")}
        ),
        result_path=sfn.JsonPath.DISCARD,  # keep the state intact; the step only has side effects in S3 and DynamoDB
        retry_on_service_exceptions=False,
    )
    translate.add_retry(errors=["Lambda.TooManyRequestsException"], max_attempts=2, interval=Duration.seconds(30))
    translate.add_catch(sfn.Pass(scope, "TranslationSkipped"), errors=["States.ALL"], result_path="$.translationError")

    follow_up: sfn.IChainable = translate
    if questions is not None:
        draft = tasks.LambdaInvoke(
            scope,
            "InvokeQuestions",
            lambda_function=questions,
            payload=sfn.TaskInput.from_object({"passageId": sfn.JsonPath.string_at("$.passageId")}),
            result_path="$.questions",  # ADD the result to the state: replacing it would lose passageId for the translation step
            retry_on_service_exceptions=False,  # no retry loop: a failed draft is simply skipped, and spend stays bounded
        )
        skipped = sfn.Pass(scope, "QuestionsSkipped")
        draft.add_catch(skipped, errors=["States.ALL"], result_path="$.questionsError")
        draft.next(translate)
        skipped.next(translate)
        # Questions are written in English: a Spanish passage goes straight to translation.
        follow_up = sfn.Choice(scope, "IsEnglish").when(sfn.Condition.string_equals("$.language", "en"), draft).otherwise(translate)

    # The generator reports failure by RETURNING a status, not by throwing, so only a job that is done gets follow-up steps.
    gate = sfn.Choice(scope, "ShouldFollowUp").when(sfn.Condition.string_equals("$.status", "done"), follow_up).otherwise(sfn.Succeed(scope, "NothingToFollowUp"))
    definition = invoke.next(gate)

    return sfn.StateMachine(
        scope,
        "GenerateStateMachine",
        state_machine_name="GenerateStateMachine",
        state_machine_type=sfn.StateMachineType.STANDARD,
        definition_body=sfn.DefinitionBody.from_chainable(definition),
        timeout=Duration.minutes(45),
    )
