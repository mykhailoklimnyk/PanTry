from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import LiteralString, cast

import psycopg

from komora import runtime
from komora.config import settings
from komora.db.canonical import canonical
from komora.logging import get_logger

log = get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"

_BOOTSTRAP = """
create table if not exists schema_migrations (
    version    text primary key,
    applied_at timestamptz not null default now(),
    checksum   text
)
"""

_ADD_CHECKSUM = "alter table schema_migrations add column if not exists checksum text"


def discover(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"немає каталогу міграцій: {directory}")
    return sorted(directory.glob("*.sql"))


async def apply_all(dsn: str | None = None, directory: Path = MIGRATIONS_DIR) -> list[str]:
    applied: list[str] = []

    async with await psycopg.AsyncConnection.connect(
        dsn or settings.database_url, connect_timeout=10
    ) as conn:
        await conn.execute(_BOOTSTRAP)
        await conn.execute(_ADD_CHECKSUM)
        await conn.commit()

        cursor = await conn.execute("select version, checksum from schema_migrations")
        known = {row[0]: row[1] for row in await cursor.fetchall()}

        for path in discover(directory):
            version = path.stem
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(canonical(sql).encode("utf-8")).hexdigest()
            legacy = hashlib.sha256(sql.encode("utf-8")).hexdigest()

            if version in known:
                stored = known[version]
                if stored is None or stored == legacy:
                    await conn.execute(
                        "update schema_migrations set checksum = %s where version = %s",
                        (checksum, version),
                    )
                    await conn.commit()
                elif stored != checksum:
                    raise RuntimeError(
                        f"міграцію {version} змінено після застосування "
                        f"(checksum {stored[:12]}… → {checksum[:12]}…). "
                        "Зміни схеми — тільки НОВИМ файлом міграції. "
                        "Сума рахується з SQL без коментарів, тож розійшовся "
                        "саме код. База, заведена до 22.08, могла лишитись із "
                        "сумою по байтах — як її перевести, у docs/deploy.md."
                    )
                continue

            log.info("migration.apply", version=version)
            async with conn.transaction():
                await conn.execute(cast(LiteralString, sql))
                await conn.execute(
                    "insert into schema_migrations (version, checksum) values (%s, %s)",
                    (version, checksum),
                )
            applied.append(version)

    if not applied:
        log.info("migration.up_to_date")
    return applied


def main() -> int:
    runtime.console()
    try:
        applied = runtime.run(apply_all())
    except Exception as exc:
        log.error("migration.failed", error=str(exc))
        return 1
    print(f"застосовано міграцій: {len(applied)}" + (f" → {', '.join(applied)}" if applied else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
