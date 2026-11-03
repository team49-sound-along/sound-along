import * as fs from 'node:fs';
import { Annotations, CfnOutput, Duration, RemovalPolicy, Stack, StackProps, Tags, aws_cloudfront as cloudfront, aws_dynamodb as dynamodb, aws_lambda as lambda, aws_s3 as s3, aws_s3_deployment as s3deploy, aws_stepfunctions as sfn, aws_stepfunctions_tasks as tasks } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { CostBudget } from './budget';
import { createSiteDistribution } from './cdn';
import { PROJECT_TAG, SourcePaths, defaultSourcePaths } from './config';
import { createApiFunction, createGeneratorFunction } from './functions';

export interface SoundAlongStackProps extends StackProps {
  /** When set, creates a monthly cost budget with email alerts. Optional: sandboxes may block the Budgets API. */
  readonly alertEmail?: string;
  readonly sources?: SourcePaths;
}

const LAMBDA_RETRY_ERRORS = [
  'Lambda.ServiceException',
  'Lambda.AWSLambdaException',
  'Lambda.SdkClientException',
  // Reserved concurrency is only 2, so throttling is an expected transient error.
  'Lambda.TooManyRequestsException',
];

export class SoundAlongStack extends Stack {
  constructor(scope: Construct, id: string, props: SoundAlongStackProps) {
    super(scope, id, props);
    const sources = props.sources ?? defaultSourcePaths();
    Tags.of(this).add('project', PROJECT_TAG);

    const bucket = new s3.Bucket(this, 'Bucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      lifecycleRules: [{ prefix: 'raw/', expiration: Duration.days(7) }],
    });

    const table = new dynamodb.Table(this, 'Table', {
      partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'sk', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl',
      removalPolicy: RemovalPolicy.DESTROY,
    });

    const generator = createGeneratorFunction(this, { generatorDir: sources.generatorDir, bucket, table });
    const stateMachine = this.createStateMachine(generator);

    const api = createApiFunction(this, { apiRoot: sources.apiRoot, bucket, table });
    api.addEnvironment('STATE_MACHINE_ARN', stateMachine.stateMachineArn);
    stateMachine.grantStartExecution(api);

    const distribution = createSiteDistribution(this, { bucket, apiFunction: api });
    this.deployWebApp(sources.webDist, bucket, distribution);

    if (props.alertEmail) {
      new CostBudget(this, 'CostBudget', { alertEmail: props.alertEmail });
    } else {
      Annotations.of(this).addInfo('No cost budget created. Pass -c alertEmail=you@example.com to add one.');
    }

    new CfnOutput(this, 'SiteUrl', { value: `https://${distribution.distributionDomainName}` });
    new CfnOutput(this, 'BucketName', { value: bucket.bucketName });
    new CfnOutput(this, 'TableName', { value: table.tableName });
    new CfnOutput(this, 'StateMachineArn', { value: stateMachine.stateMachineArn });
  }

  private createStateMachine(generator: lambda.IFunction): sfn.StateMachine {
    const invoke = new tasks.LambdaInvoke(this, 'InvokeGenerator', {
      lambdaFunction: generator,
      // Default payload is the whole execution input; unwrap the Lambda response envelope.
      outputPath: '$.Payload',
      retryOnServiceExceptions: false,
    }).addRetry({ errors: LAMBDA_RETRY_ERRORS, maxAttempts: 1, interval: Duration.seconds(5) });

    return new sfn.StateMachine(this, 'GenerateStateMachine', {
      stateMachineName: 'GenerateStateMachine',
      stateMachineType: sfn.StateMachineType.STANDARD,
      definitionBody: sfn.DefinitionBody.fromChainable(invoke),
      timeout: Duration.minutes(15),
    });
  }

  private deployWebApp(webDist: string, bucket: s3.IBucket, distribution: cloudfront.IDistribution): void {
    if (!fs.existsSync(webDist)) {
      Annotations.of(this).addWarning(
        `Web build not found at ${webDist}; skipping BucketDeployment. Run "npm run build" in web/ and synth again.`,
      );
      return;
    }
    new s3deploy.BucketDeployment(this, 'WebDeployment', {
      sources: [s3deploy.Source.asset(webDist)],
      destinationBucket: bucket,
      destinationKeyPrefix: 'app',
      distribution,
      distributionPaths: ['/*'],
      memoryLimit: 512,
    });
  }
}
