#!/usr/bin/env node
import { App } from 'aws-cdk-lib';
import { REGION } from '../lib/config';
import { SoundAlongStack } from '../lib/sound-along-stack';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const app = new App();
// The cost budget is optional: some sandbox accounts block the Budgets API, and a failed CreateBudget would roll
// back the whole stack. Pass -c alertEmail=you@example.com to create it.
const alertEmail: unknown = app.node.tryGetContext('alertEmail');
if (alertEmail !== undefined && (typeof alertEmail !== 'string' || !EMAIL_PATTERN.test(alertEmail))) {
  throw new Error('Invalid CDK context "alertEmail". Use: cdk deploy -c alertEmail=you@example.com');
}

new SoundAlongStack(app, 'SoundAlongStack', {
  alertEmail: alertEmail as string | undefined,
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: REGION },
});
