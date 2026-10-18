#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

LOCK_FILE="${TMPDIR:-/tmp}/gamesavior-march7th-image-update.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "March7thAssistant update is already running."
    exit 0
fi

PAUSE_FILE="$PROJECT_ROOT/starrail/control/.pause-for-march7th-update"
DRAIN_TIMEOUT_SECONDS="${UPDATE_DRAIN_TIMEOUT_SECONDS:-21600}"

active_run_count() {
    docker compose exec -T api python -c '
from app.db import connect
connection = connect()
count = connection.execute(
    "SELECT COUNT(*) FROM task_runs r JOIN tasks t ON t.id = r.task_id "
    "WHERE t.game = ? AND r.status IN (?, ?)",
    ("starrail", "claimed", "running"),
).fetchone()[0]
print(count)
connection.close()
' | tr -d '[:space:]'
}

worker_supports_pause() {
    docker compose exec -T api python -c '
import json
from app.db import connect
connection = connect()
row = connection.execute(
    "SELECT capabilities_json FROM workers WHERE worker_key = ?",
    ("starrail-01",),
).fetchone()
print("true" if row and json.loads(row[0]).get("pause_for_update") else "false")
connection.close()
' | tr -d '[:space:]'
}

echo "Checking the March7thAssistant image configured for this deployment..."
worker_image_ref="$(docker compose config --format json | python3 -c 'import json, sys; print(json.load(sys.stdin)["services"]["starrail-worker"]["image"])')"
worker_container="$(docker compose ps -q starrail-worker)"
before_image=""
if [[ -n "$worker_container" ]]; then
    before_image="$(docker inspect "$worker_container" --format '{{.Image}}')"
fi
docker compose build --pull --quiet starrail-worker
after_image="$(docker image inspect "$worker_image_ref" --format '{{.Id}}')"

if [[ "$before_image" == "$after_image" ]]; then
    echo "March7thAssistant image is unchanged."
    exit 0
fi

if [[ "$(worker_supports_pause)" != "true" ]]; then
    echo "The running Worker does not support safe update pausing. Deploy the current Game Savior Worker once before enabling scheduled updates." >&2
    exit 1
fi

mkdir -p "$(dirname "$PAUSE_FILE")"
touch "$PAUSE_FILE"
trap 'rm -f "$PAUSE_FILE"' EXIT

echo "A new image is available. Waiting for the current Star Rail task to finish..."
deadline=$((SECONDS + DRAIN_TIMEOUT_SECONDS))
while :; do
    active_runs="$(active_run_count)"
    if [[ "$active_runs" == "0" ]]; then
        break
    fi
    if (( SECONDS >= deadline )); then
        echo "Timed out waiting for $active_runs active task(s); the Worker will resume and the next timer run will retry." >&2
        exit 1
    fi
    sleep 15
done

echo "Updating the starrail-worker container..."
docker compose up -d --no-deps starrail-worker
echo "March7thAssistant Worker update completed."
