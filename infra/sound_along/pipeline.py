from __future__ import annotations

from aws_cdk import Duration
from aws_cdk import aws_dynamodb as dynamodb
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


def create_state_machine(scope: Construct, generator: lambda_.IFunction, questions: lambda_.IFunction | None = None, table: dynamodb.ITable | None = None) -> sfn.StateMachine:
    """For each part (one for an ordinary passage): generator -> (only if it reported done) -> questions for ENGLISH passages -> translation. Questions and translation are best effort: each has
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
    # A part that crashes (a Lambda timeout, say) must not stop the parts after it: the generator reports ordinary failures by returning a status.
    # A crash (a Lambda timeout, an out-of-memory kill) leaves the part's JOB item "running"; record the failure so the page shows it and the slot is freed.
    if table is not None:
        attr = tasks.DynamoAttributeValue
        part_failed: sfn.IChainable = tasks.DynamoUpdateItem(
            scope, "PartFailed", table=table,
            key={"pk": attr.from_string("JOB"), "sk": attr.from_string(sfn.JsonPath.string_at("$.jobId"))},
            condition_expression="attribute_exists(pk)",
            update_expression="SET #s = :failed, #e = :msg, finishedAt = :now",
            expression_attribute_names={"#s": "status", "#e": "error"},
            expression_attribute_values={
                ":failed": attr.from_string("failed"),
                ":msg": attr.from_string("We could not finish creating the audio for this part. Please try again in a moment."),
                ":now": attr.from_string(sfn.JsonPath.string_at("$$.State.EnteredTime")),
            },
            result_path=sfn.JsonPath.DISCARD,
        )
        part_failed.add_catch(sfn.Pass(scope, "PartFailedUnrecorded"), errors=["States.ALL"], result_path="$.recordError")
    else:
        part_failed = sfn.Pass(scope, "PartFailed")
    invoke.add_catch(part_failed, errors=["States.ALL"], result_path="$.partError")
    one_part = invoke.next(gate)

    # One execution per submitted document. The input is {"parts": [{jobId, passageId, title, rawKey, humanPassageId}, ...]} (one entry for an ordinary
    # passage). The parts run ONE AT A TIME: the generator has only 2 reserved slots and a part is 5 to 10 minutes of work, so queueing on Lambda throttles
    # would burn the execution's time. Only keys travel between states (the 256 KB state limit); the text is in S3.
    definition = sfn.Map(scope, "EachPart", items_path="$.parts", max_concurrency=1, result_path=sfn.JsonPath.DISCARD).item_processor(one_part)

    return sfn.StateMachine(
        scope,
        "GenerateStateMachine",
        state_machine_name="GenerateStateMachine",
        state_machine_type=sfn.StateMachineType.STANDARD,
        definition_body=sfn.DefinitionBody.from_chainable(definition),
        timeout=Duration.hours(8),  # worst case: 12 parts x (900 s generator + 120 s questions + 900 s translation) is 6.4 hours; a typical part takes about 10 minutes
    )
