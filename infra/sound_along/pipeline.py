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
    """Standard state machine: the generator, then (only if it reported done) a best-effort questions step that can never fail the job."""
    invoke = tasks.LambdaInvoke(
        scope,
        "InvokeGenerator",
        lambda_function=generator,
        # Default payload is the whole execution input; unwrap the Lambda response envelope.
        output_path="$.Payload",
        retry_on_service_exceptions=False,
    ).add_retry(errors=list(LAMBDA_RETRY_ERRORS), max_attempts=1, interval=Duration.seconds(5))

    definition: sfn.IChainable = invoke
    if questions is not None:
        draft = tasks.LambdaInvoke(
            scope,
            "InvokeQuestions",
            lambda_function=questions,
            payload=sfn.TaskInput.from_object({"passageId": sfn.JsonPath.string_at("$.passageId")}),
            output_path="$.Payload",
            retry_on_service_exceptions=False,  # no retry loop: a failed draft is simply skipped, and spend stays bounded
        )
        draft.add_catch(sfn.Pass(scope, "QuestionsSkipped"), errors=["States.ALL"], result_path="$.questionsError")
        # The generator reports failure by RETURNING a status, not by throwing, so only a job that is done gets questions.
        gate = sfn.Choice(scope, "ShouldDraftQuestions").when(sfn.Condition.string_equals("$.status", "done"), draft).otherwise(sfn.Succeed(scope, "NoQuestionsNeeded"))
        definition = invoke.next(gate)

    return sfn.StateMachine(
        scope,
        "GenerateStateMachine",
        state_machine_name="GenerateStateMachine",
        state_machine_type=sfn.StateMachineType.STANDARD,
        definition_body=sfn.DefinitionBody.from_chainable(definition),
        timeout=Duration.minutes(15),
    )
