import { strict as assert } from 'node:assert';
import * as path from 'node:path';
import { before, describe, it } from 'node:test';
import { App } from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { SoundAlongStack } from '../lib/sound-along-stack';

const FIXTURES = path.join(__dirname, 'fixtures');
const SOURCES = {
  apiRoot: path.join(FIXTURES, 'api'),
  generatorDir: path.join(FIXTURES, 'generator'),
  webDist: path.join(FIXTURES, 'web-dist'),
};

let template: Template;

before(() => {
  const app = new App();
  const stack = new SoundAlongStack(app, 'TestStack', {
    alertEmail: 'test@example.com',
    sources: SOURCES,
    env: { region: 'us-west-2' },
  });
  template = Template.fromStack(stack);
});

interface PolicyDoc {
  Statement: { Action: string | string[]; Effect: string }[];
}

function actionsForRolesStartingWith(prefix: string): string[] {
  const policies = template.findResources('AWS::IAM::Policy');
  const actions: string[] = [];
  for (const policy of Object.values(policies)) {
    const props = policy.Properties as { Roles: { Ref: string }[]; PolicyDocument: PolicyDoc };
    if (!props.Roles.some((role) => role.Ref.startsWith(prefix))) continue;
    for (const statement of props.PolicyDocument.Statement) {
      actions.push(...[statement.Action].flat());
    }
  }
  return actions;
}

describe('SoundAlongStack', () => {
  it('has a private, encrypted, SSL-only bucket with raw/ expiry', () => {
    template.hasResourceProperties('AWS::S3::Bucket', {
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true, BlockPublicPolicy: true, IgnorePublicAcls: true, RestrictPublicBuckets: true,
      },
      BucketEncryption: { ServerSideEncryptionConfiguration: Match.anyValue() },
      LifecycleConfiguration: {
        Rules: [Match.objectLike({ Prefix: 'raw/', ExpirationInDays: 7, Status: 'Enabled' })],
      },
    });
    template.hasResourceProperties('AWS::S3::BucketPolicy', {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({ Effect: 'Deny', Condition: { Bool: { 'aws:SecureTransport': 'false' } } }),
        ]),
      },
    });
  });

  it('uses OAC and three behaviors', () => {
    template.resourceCountIs('AWS::CloudFront::OriginAccessControl', 2); // S3 + Lambda URL
    template.hasResourceProperties('AWS::CloudFront::Distribution', {
      DistributionConfig: {
        DefaultRootObject: 'index.html',
        DefaultCacheBehavior: Match.objectLike({ ViewerProtocolPolicy: 'redirect-to-https', Compress: true }),
        CacheBehaviors: [
          Match.objectLike({ PathPattern: '/data/*', AllowedMethods: ['GET', 'HEAD'] }),
          Match.objectLike({
            PathPattern: '/api/*',
            AllowedMethods: ['GET', 'HEAD', 'OPTIONS', 'PUT', 'PATCH', 'POST', 'DELETE'],
          }),
        ],
        Origins: Match.arrayWith([Match.objectLike({ OriginPath: '/app' })]),
      },
    });
    template.hasResourceProperties('AWS::Lambda::Url', { AuthType: 'AWS_IAM' });
  });

  it('configures the API Lambda', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      Runtime: 'nodejs22.x',
      Architectures: ['arm64'],
      MemorySize: 512,
      Timeout: 30,
      ReservedConcurrentExecutions: 5,
      Environment: { Variables: Match.objectLike({ GENERATION_ENABLED: 'true', BUCKET: Match.anyValue(), TABLE_NAME: Match.anyValue(), STATE_MACHINE_ARN: Match.anyValue() }) },
    });
  });

  it('configures the generator container Lambda', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      PackageType: 'Image',
      Architectures: ['arm64'],
      MemorySize: 4096,
      Timeout: 600,
      ReservedConcurrentExecutions: 2,
      Environment: { Variables: { BUCKET: Match.anyValue(), TABLE_NAME: Match.anyValue() } },
    });
  });

  it('defines the Standard state machine with one retrying task', () => {
    template.hasResourceProperties('AWS::StepFunctions::StateMachine', {
      StateMachineName: 'GenerateStateMachine',
      StateMachineType: 'STANDARD',
      DefinitionString: Match.anyValue(),
    });
    const machines = Object.values(template.findResources('AWS::StepFunctions::StateMachine'));
    const definition = JSON.stringify(machines[0].Properties.DefinitionString);
    assert.match(definition, /Retry/);
    assert.match(definition, /MaxAttempts\D+1\b/);
    assert.doesNotMatch(definition, /States\.TaskFailed/);
    assert.match(definition, /Payload\.\$/);
    assert.match(definition, /TimeoutSeconds\D+900\b/);
  });

  it('has an on-demand table with ttl', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      BillingMode: 'PAY_PER_REQUEST',
      TimeToLiveSpecification: { AttributeName: 'ttl', Enabled: true },
      KeySchema: [{ AttributeName: 'pk', KeyType: 'HASH' }, { AttributeName: 'sk', KeyType: 'RANGE' }],
    });
  });

  it('creates budget alerts at 25/50/80 percent', () => {
    const budgets = Object.values(template.findResources('AWS::Budgets::Budget'));
    assert.equal(budgets.length, 1);
    const props = budgets[0].Properties as {
      Budget: { BudgetLimit: { Amount: number } };
      NotificationsWithSubscribers: { Notification: { Threshold: number; NotificationType: string } }[];
    };
    assert.equal(props.Budget.BudgetLimit.Amount, 500);
    assert.deepEqual(props.NotificationsWithSubscribers.map((n) => n.Notification.Threshold), [25, 50, 80]);
    assert.ok(props.NotificationsWithSubscribers.every((n) => n.Notification.NotificationType === 'ACTUAL'));
  });

  it('deploys the web app and exposes outputs', () => {
    template.resourceCountIs('Custom::CDKBucketDeployment', 1);
    for (const name of ['SiteUrl', 'BucketName', 'TableName', 'StateMachineArn']) {
      assert.ok(name in template.toJSON().Outputs, `missing output ${name}`);
    }
  });

  it('grants no service-wide wildcard actions to workload roles', () => {
    for (const prefix of ['ApiFunctionServiceRole', 'GeneratorFunctionServiceRole', 'GenerateStateMachineRole']) {
      const actions = actionsForRolesStartingWith(prefix);
      assert.ok(actions.length > 0, `no policy found for ${prefix}`);
      const wildcards = actions.filter((a) => a === '*' || a.endsWith(':*') || a.endsWith('*'));
      assert.deepEqual(wildcards, [], `${prefix} has wildcard actions`);
    }
  });

  it('scopes S3 access by prefix', () => {
    const api = actionsForRolesStartingWith('ApiFunctionServiceRole');
    assert.ok(api.includes('s3:PutObject'));
    assert.ok(!api.some((a) => a.startsWith('s3:Get')));
    assert.ok(actionsForRolesStartingWith('ApiFunctionServiceRole').includes('states:StartExecution'));
  });
});

describe('without alertEmail', () => {
  it('creates no budget, so a sandbox that blocks the Budgets API cannot fail the deploy', () => {
    const app = new App();
    const stack = new SoundAlongStack(app, 'NoBudgetStack', { sources: SOURCES, env: { region: 'us-west-2' } });
    assert.equal(Object.keys(Template.fromStack(stack).findResources('AWS::Budgets::Budget')).length, 0);
  });
});
