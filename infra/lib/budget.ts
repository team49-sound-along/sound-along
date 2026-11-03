import { aws_budgets as budgets } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { BUDGET_LIMIT_USD, BUDGET_THRESHOLD_PERCENTS } from './config';

export interface CostBudgetProps {
  readonly alertEmail: string;
}

/** Monthly cost budget with email alerts on actual spend. */
export class CostBudget extends Construct {
  constructor(scope: Construct, id: string, props: CostBudgetProps) {
    super(scope, id);
    new budgets.CfnBudget(this, 'Budget', {
      budget: {
        budgetName: 'sound-along-monthly',
        budgetType: 'COST',
        timeUnit: 'MONTHLY',
        budgetLimit: { amount: BUDGET_LIMIT_USD, unit: 'USD' },
      },
      notificationsWithSubscribers: BUDGET_THRESHOLD_PERCENTS.map((threshold) => ({
        notification: {
          notificationType: 'ACTUAL',
          comparisonOperator: 'GREATER_THAN',
          thresholdType: 'PERCENTAGE',
          threshold,
        },
        subscribers: [{ subscriptionType: 'EMAIL', address: props.alertEmail }],
      })),
    });
  }
}
