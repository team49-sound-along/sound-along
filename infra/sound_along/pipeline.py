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


def create_state_machine(scope: Construct, generator: lambda_.IFunction) -> sfn.StateMachine:
    """Standard state machine with a single retrying task that invokes the generator."""
    invoke = tasks.LambdaInvoke(
        scope,
        "InvokeGenerator",
        lambda_function=generator,
        # Default payload is the whole execution input; unwrap the Lambda response envelope.
        output_path="$.Payload",
        retry_on_service_exceptions=False,
    ).add_retry(errors=list(LAMBDA_RETRY_ERRORS), max_attempts=1, interval=Duration.seconds(5))

    return sfn.StateMachine(
        scope,
        "GenerateStateMachine",
        state_machine_name="GenerateStateMachine",
        state_machine_type=sfn.StateMachineType.STANDARD,
        definition_body=sfn.DefinitionBody.from_chainable(invoke),
        timeout=Duration.minutes(15),
    )
