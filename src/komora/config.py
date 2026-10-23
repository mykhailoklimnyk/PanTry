from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KOMORA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://komora@localhost:5433/komora"

    mcp_url: str = "https://mcp.silpo.ua/mcp"
    mcp_token: str | None = None
    branch_id: str | None = None

    watch_branch_ids: str = ""

    stock_batch_limit: int = 60

    def watch_branches(self) -> tuple[str, ...]:
        ids = [part.strip() for part in self.watch_branch_ids.split(",") if part.strip()]
        if not ids and self.branch_id:
            ids = [self.branch_id]
        return tuple(dict.fromkeys(ids))

    bedrock_base_url: str = Field(
        default="https://bedrock-mantle.us-east-1.api.aws/anthropic",
        alias="ANTHROPIC_BASE_URL",
    )
    bedrock_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    bedrock_model_id: str = Field(
        default="mistral.mistral-large-3-675b-instruct", alias="ANTHROPIC_MODEL_MAIN"
    )
    bedrock_model_cheap: str = Field(
        default="mistral.devstral-2-123b", alias="ANTHROPIC_MODEL_CHEAP"
    )
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")

    openai_base_url: str = Field(default="https://api.openai.com", alias="OPENAI_BASE_URL")

    pick_batches: int = 1

    pantry_turns: int = 4

    pantry_batches: int = 2

    run_log: bool = False

    session_key: str = ""

    public_url: str = "https://pantry.klimnyk.dev"

    oauth_client_id: str = ""

    @property
    def guest_login_ready(self) -> bool:
        return bool(self.session_key.strip())

    insiders: str = ""

    def insider_accounts(self) -> frozenset[str]:
        return frozenset(part.strip() for part in self.insiders.split(",") if part.strip())

    runs_per_session: int = 6

    runs_per_day: int = 12

    budget_day_usd: Decimal = Decimal("2.00")

    budget_total_usd: Decimal = Decimal("40.00")

    contact: str = "https://github.com/mykhailoklimnyk/pantry/issues"

    telegram_token: str | None = None
    telegram_chat: str | None = None

    log_level: Literal["debug", "info", "warning", "error"] = "info"

    mcp_max_attempts: int = 4
    mcp_backoff_base_s: float = 1.5
    mcp_timeout_s: float = 60.0

    def operator_token(self) -> str | None:
        if self.mcp_token:
            return self.mcp_token

        token_file = Path(__file__).resolve().parents[2] / ".mcp-token.json"
        if not token_file.exists():
            return None
        try:
            saved = json.loads(token_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return (saved.get("tokens") or {}).get("access_token")

    def require_operator(self) -> tuple[str, str]:
        token = self.operator_token()
        if not token:
            raise RuntimeError(
                "Немає токена оператора. Виконай `uv run python scripts/mcp_login.py` "
                "або задай KOMORA_MCP_TOKEN. Крон слотів без нього не працює. "
                "Див. docs/setup.md."
            )
        if not self.branch_id:
            raise RuntimeError(
                "KOMORA_BRANCH_ID не заданий. На акаунті з кошиком береться з "
                "silpo_get_shopping_cart_by_id → cart.shipments[0].branchId; "
                "на чистому акаунті — з silpo_get_available_delivery_types за координатами."
            )
        return token, self.branch_id


settings = Settings()
