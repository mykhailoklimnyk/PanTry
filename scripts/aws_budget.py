from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from typing import Any

from komora import runtime
from komora.config import settings
from komora.core.quota import PRICES

runtime.console()

BUDGET_NAME = "komora-bedrock"

THRESHOLDS = (50.0, 80.0, 100.0)

SERVICE = "Amazon Bedrock"


def _client(service: str) -> Any:
    try:
        import boto3
    except ImportError:  # pragma: no cover — boto3 приходить з anthropic[bedrock]
        raise SystemExit("Немає boto3. Постав залежності: uv sync") from None
    return boto3.client(service)


def account_id() -> str:
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        return str(_client("sts").get_caller_identity()["Account"])
    except (BotoCoreError, ClientError) as exc:
        raise SystemExit(
            "AWS не впізнав нас: "
            f"{type(exc).__name__}. Потрібні звичайні креденшели (AWS_PROFILE або "
            "ключі в оточенні) з правами budgets:ModifyBudget. Ключ Bedrock "
            "(ABSK...) сюди не годиться — він відмикає інференс, а не білінг. "
            "Покроково руками — docs/deploy.md."
        ) from exc


def budget_body(limit: Decimal) -> dict[str, Any]:
    return {
        "BudgetName": BUDGET_NAME,
        "BudgetLimit": {"Amount": str(limit), "Unit": "USD"},
        "CostFilters": {"Service": [SERVICE]},
        "CostTypes": {
            "IncludeTax": True,
            "IncludeSubscription": True,
            "UseBlended": False,
            "IncludeRefund": False,
            "IncludeCredit": False,
            "IncludeUpfront": True,
            "IncludeRecurring": True,
            "IncludeOtherSubscription": True,
            "IncludeSupport": True,
            "IncludeDiscount": True,
            "UseAmortized": False,
        },
        "TimeUnit": "MONTHLY",
        "BudgetType": "COST",
    }


def notifications(emails: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "Notification": {
                "NotificationType": "ACTUAL",
                "ComparisonOperator": "GREATER_THAN",
                "Threshold": threshold,
                "ThresholdType": "PERCENTAGE",
            },
            "Subscribers": [
                {"SubscriptionType": "EMAIL", "Address": email} for email in emails
            ],
        }
        for threshold in THRESHOLDS
    ]


def show(account: str) -> int:
    from botocore.exceptions import ClientError

    budgets = _client("budgets")
    try:
        found = budgets.describe_budget(AccountId=account, BudgetName=BUDGET_NAME)["Budget"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NotFoundException":
            print(f"Бюджету «{BUDGET_NAME}» немає. Постав його: --email <адреса>")
            return 1
        raise

    limit = found["BudgetLimit"]
    print(f"Бюджет «{BUDGET_NAME}»: {limit['Amount']} {limit['Unit']} / {found['TimeUnit']}")
    print(f"  фільтр: {found.get('CostFilters') or 'немає — рахується ВЕСЬ акаунт'}")

    pairs = budgets.describe_notifications_for_budget(
        AccountId=account, BudgetName=BUDGET_NAME
    )["Notifications"]
    if not pairs:
        print("  порогів немає — бюджет мовчазний, тобто марний")
        return 1
    for note in pairs:
        subs = budgets.describe_subscribers_for_notification(
            AccountId=account, BudgetName=BUDGET_NAME, Notification=note
        )["Subscribers"]
        where = ", ".join(sub["Address"] for sub in subs) or "нікому"
        print(f"  {note['Threshold']:.0f}% {note['NotificationType']} → {where}")
    return 0


def put(account: str, *, limit: Decimal, emails: list[str]) -> int:
    from botocore.exceptions import ClientError

    budgets = _client("budgets")
    body = budget_body(limit)
    notes = notifications(emails)

    try:
        budgets.create_budget(
            AccountId=account, Budget=body, NotificationsWithSubscribers=notes
        )
        print(f"Бюджет «{BUDGET_NAME}» створено: {limit} USD/міс на «{SERVICE}»")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "DuplicateRecordException":
            raise
        budgets.update_budget(AccountId=account, NewBudget=body)
        _resubscribe(budgets, account, notes)
        print(f"Бюджет «{BUDGET_NAME}» оновлено: {limit} USD/міс на «{SERVICE}»")

    print(f"Пороги: {', '.join(f'{value:.0f}%' for value in THRESHOLDS)} → {', '.join(emails)}")
    print(
        "Перший лист AWS попросить підтвердити адресу — без підтвердження "
        "алярм стоїть, але мовчить."
    )
    return 0


def _resubscribe(budgets: Any, account: str, notes: list[dict[str, Any]]) -> None:
    for old in budgets.describe_notifications_for_budget(
        AccountId=account, BudgetName=BUDGET_NAME
    )["Notifications"]:
        budgets.delete_notification(
            AccountId=account, BudgetName=BUDGET_NAME, Notification=old
        )
    for note in notes:
        budgets.create_notification(
            AccountId=account,
            BudgetName=BUDGET_NAME,
            Notification=note["Notification"],
            Subscribers=note["Subscribers"],
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="лише показати, що стоїть зараз"
    )
    parser.add_argument(
        "--email",
        action="append",
        default=[],
        help="куди слати лист; можна кілька разів",
    )
    parser.add_argument(
        "--limit",
        type=Decimal,
        default=None,
        help=(
            "місячна межа в доларах. Замовчування — наша власна стеля "
            "(KOMORA_BUDGET_TOTAL_USD), щоб алярм і лічильник міряли одне й те саме"
        ),
    )
    args = parser.parse_args(argv)

    if not args.check and not args.email:
        parser.error("потрібен --email: бюджет без адреси нікому не пише, тобто марний")

    account = account_id()
    if args.check:
        return show(account)

    limit = args.limit if args.limit is not None else settings.budget_total_usd
    print(f"Прайс, з якого рахує наш лічильник: {len(PRICES)} моделі (core/quota.PRICES)")
    return put(account, limit=limit, emails=args.email)


if __name__ == "__main__":
    sys.exit(main())
