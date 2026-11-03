import * as path from 'node:path';
import { Duration, RemovalPolicy, aws_dynamodb as dynamodb, aws_ecr_assets as ecrAssets, aws_iam as iam, aws_lambda as lambda, aws_logs as logs, aws_s3 as s3 } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { bundleNodeEntry } from './bundling';

function logGroup(scope: Construct, id: string): logs.LogGroup {
  return new logs.LogGroup(scope, id, {
    retention: logs.RetentionDays.ONE_WEEK,
    removalPolicy: RemovalPolicy.DESTROY,
  });
}

/** Object-level S3 access only; avoids the s3:Abort* / s3:PutObject* wildcards of bucket.grantPut. */
function allowObjects(fn: lambda.IFunction, bucket: s3.IBucket, actions: string[], prefix: string): void {
  fn.addToRolePolicy(
    new iam.PolicyStatement({ actions, resources: [bucket.arnForObjects(prefix)] }),
  );
}

export interface ApiFunctionProps {
  readonly apiRoot: string;
  readonly bucket: s3.IBucket;
  readonly table: dynamodb.ITable;
}

export function createApiFunction(scope: Construct, props: ApiFunctionProps): lambda.Function {
  const fn = new lambda.Function(scope, 'ApiFunction', {
    code: bundleNodeEntry(props.apiRoot, path.join('src', 'aws', 'lambda.js')),
    handler: 'index.handler',
    runtime: lambda.Runtime.NODEJS_22_X,
    architecture: lambda.Architecture.ARM_64,
    memorySize: 512,
    timeout: Duration.seconds(30),
    reservedConcurrentExecutions: 5,
    logGroup: logGroup(scope, 'ApiLogs'),
    environment: {
      BUCKET: props.bucket.bucketName,
      TABLE_NAME: props.table.tableName,
      GENERATION_ENABLED: 'true',
      GENERATE_PER_MINUTE: '3',
      MAX_CONCURRENT_JOBS: '2',
    },
  });
  props.table.grantReadWriteData(fn);
  allowObjects(fn, props.bucket, ['s3:PutObject'], 'raw/*');
  return fn;
}

export interface GeneratorFunctionProps {
  readonly generatorDir: string;
  readonly bucket: s3.IBucket;
  readonly table: dynamodb.ITable;
}

export function createGeneratorFunction(scope: Construct, props: GeneratorFunctionProps): lambda.DockerImageFunction {
  const fn = new lambda.DockerImageFunction(scope, 'GeneratorFunction', {
    code: lambda.DockerImageCode.fromImageAsset(props.generatorDir, { platform: ecrAssets.Platform.LINUX_ARM64 }),
    architecture: lambda.Architecture.ARM_64,
    memorySize: 4096,
    timeout: Duration.seconds(600),
    reservedConcurrentExecutions: 2,
    logGroup: logGroup(scope, 'GeneratorLogs'),
    environment: { BUCKET: props.bucket.bucketName, TABLE_NAME: props.table.tableName },
  });
  props.table.grantReadWriteData(fn);
  allowObjects(fn, props.bucket, ['s3:GetObject'], 'raw/*');
  allowObjects(fn, props.bucket, ['s3:PutObject'], 'data/*');
  return fn;
}
