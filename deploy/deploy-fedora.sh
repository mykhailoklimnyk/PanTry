#!/usr/bin/env bash
set -euo pipefail

APP=/opt/komora
export PATH="$HOME/.local/bin:$PATH"

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

cd "$APP"

echo "== версія =="
cat .deployed-sha 2>/dev/null || echo "(мітку коміта не записано — ручний запуск)"

echo "== залежності =="
uv sync --locked

echo "== міграції =="
uv run komora-migrate

echo "== перевірка бази =="
uv run python -c "
import asyncio, psycopg
from komora.config import settings
async def main():
    async with await psycopg.AsyncConnection.connect(settings.database_url) as c:
        cur = await c.execute('select count(*) from slot_snapshots')
        print('знімків слотів у базі:', (await cur.fetchone())[0])
asyncio.run(main())
"

echo "== systemd-юніти =="
for installed in "$HOME"/.config/systemd/user/komora-*.service "$HOME"/.config/systemd/user/komora-*.timer; do
  [ -e "$installed" ] || continue
  name=$(basename "$installed")
  if [ ! -e "deploy/$name" ]; then
    systemctl --user disable --now "$name" >/dev/null 2>&1 || true
    rm -f "$installed"
    echo "  знято зайвий юніт: $name"
  fi
done
install -D -m 0644 -t "$HOME/.config/systemd/user/" deploy/komora-*.service
systemctl --user daemon-reload
UNITS=(
  komora-api.service
  komora-api-tunnel.service
)
for unit in "${UNITS[@]}"; do
  systemctl --user enable "$unit" >/dev/null 2>&1 || true
  systemctl --user restart "$unit"
done

echo "== готово =="
