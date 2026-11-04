from __future__ import annotations

from aws_cdk import aws_budgets as budgets
from constructs import Construct

from .config import BUDGET_LIMIT_USD, BUDGET_THRESHOLD_PERCENTS


class CostBudget(Construct):
    """Monthly cost budget with email alerts on actual spend."""

    def __init__(self, scope: Construct, construct_id: str, *, alert_email: str) -> None:
        super().__init__(scope, construct_id)
        budgets.CfnBudget(
            self,
            "Budget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                # No budget_name: let CloudFormation assign a unique physical name. A hardcoded name makes changing the
                # budget (e.g. the alert email) a replace that collides with the still-existing budget of the same name
                # ("A budget ... with the same name but a different internalId already exists"). An auto-generated name
                # lets the replacement create the new budget and then delete the old one cleanly.
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=BUDGET_LIMIT_USD, unit="USD"),
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL",
                        comparison_operator="GREATER_THAN",
                        threshold_type="PERCENTAGE",
                        threshold=threshold,
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(subscription_type="EMAIL", address=alert_email)
                    ],
                )
                for threshold in BUDGET_THRESHOLD_PERCENTS
            ],
        )
