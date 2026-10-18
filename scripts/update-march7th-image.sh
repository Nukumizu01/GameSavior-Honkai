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
UPSTREAM_DIGEST_FILE="$PROJECT_ROOT/starrail/control/march7th-image.digest"
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

worker_registration() {
    docker compose exec -T api python -c '
from app.db import connect
connection = connect()
row = connection.execute(
    "SELECT status, updated_at FROM workers WHERE worker_key = ?",
    ("starrail-01",),
).fetchone()
if row:
    print("{}|{}".format(row["status"], row["updated_at"]))
else:
    print("")
connection.close()
' | tr -d '[:space:]'
}

echo "Checking the March7thAssistant image configured for this deployment..."
march7th_image_ref="$(docker compose config --format json | python3 -c 'import json, sys; print(json.load(sys.stdin)["services"]["starrail-worker"]["build"]["args"]["MARCH7TH_IMAGE"])')"
docker pull "$march7th_image_ref"
upstream_digest="$(docker image inspect "$march7th_image_ref" --format '{{index .RepoDigests 0}}')"
if [[ -z "$upstream_digest" ]]; then
    echo "Could not determine the March7thAssistant registry digest." >&2
    exit 1
fi

last_digest="$(cat "$UPSTREAM_DIGEST_FILE" 2>/dev/null || true)"
if [[ "$last_digest" == "$upstream_digest" ]]; then
    echo "March7thAssistant image is unchanged ($upstream_digest)."
    exit 0
fi

docker compose build --pull --quiet starrail-worker

if [[ "$(worker_supports_pause)" != "true" ]]; then
    echo "The running Worker does not support safe update pausing. Deploy the current Game Savior Worker once before enabling scheduled updates." >&2
    exit 1
fi
previous_registration="$(worker_registration)"

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
registered=false
for _ in {1..60}; do
    current_registration="$(worker_registration)"
    if [[ "$current_registration" == online\|* && "$current_registration" != "$previous_registration" ]]; then
        registered=true
        break
    fi
    sleep 2
done
if [[ "$registered" != "true" ]]; then
    echo "Updated Worker did not register with the API; the next timer run will retry." >&2
    exit 1
fi

printf '%s\n' "$upstream_digest" > "$UPSTREAM_DIGEST_FILE.tmp"
mv "$UPSTREAM_DIGEST_FILE.tmp" "$UPSTREAM_DIGEST_FILE"
echo "March7thAssistant Worker update completed."
