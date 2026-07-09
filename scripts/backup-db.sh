#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

sudo docker compose exec -T app python - <<'PY'
import datetime
import pathlib
import sqlite3

backup_dir = pathlib.Path("/app/data/backups")
backup_dir.mkdir(parents=True, exist_ok=True)
target = backup_dir / f"toefl_review-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3"

source = sqlite3.connect("/app/data/toefl_review.sqlite3")
destination = sqlite3.connect(target)
with destination:
    source.backup(destination)
source.close()
destination.close()

print(target)
PY
