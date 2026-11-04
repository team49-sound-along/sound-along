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
    single = sfn.Map(scope, "EachPart", items_path="$.parts", max_concurrency=1, result_path=sfn.JsonPath.DISCARD).item_processor(one_part)

    # A long document is ONE passage for the person: its chunks are narrated and translated one after another in a private work folder, the progress
    # is counted on the person's job, then ONE invocation joins them into a single passage per language (generator `stitch` mode) and questions are
    # drafted once, for the whole passage. Input: {"document": {jobId, passageId, title, rawKey, chunkIds, chunks: [{jobId, passageId, rawKey, title, workFor}]}}.
    jp = sfn.JsonPath
    chunk_fields = {"jobId": jp.string_at("$.jobId"), "passageId": jp.string_at("$.passageId"), "rawKey": jp.string_at("$.rawKey"),
                    "title": jp.string_at("$.title"), "workFor": jp.string_at("$.workFor")}
    chunk_progress: sfn.IChainable
    if table is not None:
        attr = tasks.DynamoAttributeValue
        chunk_progress = tasks.DynamoUpdateItem(
            scope, "ChunkDone", table=table,
            key={"pk": attr.from_string("JOB"), "sk": attr.from_string(jp.string_at("$.jobId"))},
            condition_expression="attribute_exists(pk)",
            update_expression="SET #s = :running, #p = :step ADD chunksDone :one",
            expression_attribute_names={"#s": "status", "#p": "step"},
            expression_attribute_values={":running": attr.from_string("running"), ":step": attr.from_string("synthesize"), ":one": attr.from_number(1)},
            result_path=sfn.JsonPath.DISCARD,
        )
        chunk_progress.add_catch(sfn.Pass(scope, "ChunkProgressUnrecorded"), errors=["States.ALL"], result_path="$.recordError")  # type: ignore[attr-defined]
    else:
        chunk_progress = sfn.Pass(scope, "ChunkDone")
    chunk_generate = tasks.LambdaInvoke(scope, "InvokeChunk", lambda_function=generator, payload=sfn.TaskInput.from_object(chunk_fields),
                                        result_path=sfn.JsonPath.DISCARD, retry_on_service_exceptions=False)
    chunk_generate.add_retry(errors=list(LAMBDA_RETRY_ERRORS), max_attempts=1, interval=Duration.seconds(5))
    chunk_translate = tasks.LambdaInvoke(scope, "InvokeChunkTranslation", lambda_function=generator, payload=sfn.TaskInput.from_object({"mode": "translate", **chunk_fields}),
                                         result_path=sfn.JsonPath.DISCARD, retry_on_service_exceptions=False)
    chunk_translate.add_retry(errors=["Lambda.TooManyRequestsException"], max_attempts=2, interval=Duration.seconds(30))
    # A chunk that crashes or whose translation fails must not stop the next one; the join checks that everything it needs exists and fails the job if not.
    chunk_skipped, translation_skipped = sfn.Pass(scope, "ChunkSkipped"), sfn.Pass(scope, "ChunkTranslationSkipped")
    chunk_skipped.next(chunk_progress)  # type: ignore[arg-type]
    translation_skipped.next(chunk_progress)  # type: ignore[arg-type]
    chunk_generate.add_catch(chunk_skipped, errors=["States.ALL"], result_path="$.chunkError")
    chunk_translate.add_catch(translation_skipped, errors=["States.ALL"], result_path="$.translationError")
    chunk_generate.next(chunk_translate)
    chunk_translate.next(chunk_progress)  # type: ignore[arg-type]
    each_chunk = sfn.Map(scope, "EachChunk", items_path="$.document.chunks", max_concurrency=1, result_path=sfn.JsonPath.DISCARD).item_processor(chunk_generate)

    stitch = tasks.LambdaInvoke(
        scope, "InvokeStitch", lambda_function=generator,
        payload=sfn.TaskInput.from_object({"mode": "stitch", "jobId": jp.string_at("$.document.jobId"), "passageId": jp.string_at("$.document.passageId"),
                                           "rawKey": jp.string_at("$.document.rawKey"), "title": jp.string_at("$.document.title"), "chunkIds": jp.list_at("$.document.chunkIds")}),
        result_path="$.stitched", retry_on_service_exceptions=False,
    )
    stitch.add_retry(errors=list(LAMBDA_RETRY_ERRORS), max_attempts=1, interval=Duration.seconds(5))
    document_failed: sfn.IChainable
    if table is not None:
        document_failed = tasks.DynamoUpdateItem(
            scope, "DocumentFailed", table=table,
            key={"pk": attr.from_string("JOB"), "sk": attr.from_string(jp.string_at("$.document.jobId"))},
            condition_expression="attribute_exists(pk)",
            update_expression="SET #s = :failed, #e = :msg, finishedAt = :now",
            expression_attribute_names={"#s": "status", "#e": "error"},
            expression_attribute_values={":failed": attr.from_string("failed"),
                                         ":msg": attr.from_string("We could not finish creating the audio for this text. Please try again in a moment."),
                                         ":now": attr.from_string(jp.string_at("$$.State.EnteredTime"))},
            result_path=sfn.JsonPath.DISCARD,
        )
        document_failed.add_catch(sfn.Pass(scope, "DocumentFailedUnrecorded"), errors=["States.ALL"], result_path="$.recordError")  # type: ignore[attr-defined]
    else:
        document_failed = sfn.Pass(scope, "DocumentFailed")
    stitch.add_catch(document_failed, errors=["States.ALL"], result_path="$.stitchError")
    after_stitch: sfn.IChainable = sfn.Succeed(scope, "DocumentDone")
    if questions is not None:
        draft_document = tasks.LambdaInvoke(scope, "InvokeDocumentQuestions", lambda_function=questions,
                                            payload=sfn.TaskInput.from_object({"passageId": jp.string_at("$.document.passageId")}),
                                            result_path="$.questions", retry_on_service_exceptions=False)
        draft_document.add_catch(sfn.Pass(scope, "DocumentQuestionsSkipped"), errors=["States.ALL"], result_path="$.questionsError")
        after_stitch = (sfn.Choice(scope, "DocumentIsEnglish")
                        .when(sfn.Condition.and_(sfn.Condition.string_equals("$.stitched.Payload.status", "done"), sfn.Condition.string_equals("$.stitched.Payload.language", "en")), draft_document)
                        .otherwise(sfn.Succeed(scope, "DocumentNoQuestions")))
    each_chunk.next(stitch)
    stitch.next(after_stitch)
    definition = sfn.Choice(scope, "IsDocument").when(sfn.Condition.is_present("$.document"), each_chunk).otherwise(single)

    return sfn.StateMachine(
        scope,
        "GenerateStateMachine",
        state_machine_name="GenerateStateMachine",
        state_machine_type=sfn.StateMachineType.STANDARD,
        definition_body=sfn.DefinitionBody.from_chainable(definition),
        timeout=Duration.hours(8),  # worst case: 12 parts x (900 s generator + 120 s questions + 900 s translation) is 6.4 hours; a typical part takes about 10 minutes
    )
