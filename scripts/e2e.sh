#!/usr/bin/env bash
# Frontend end to end against Compose (#116). Local only, like the smoke: the
# compose CI job was removed for failing on backend startup too often to gate on.
#
# Brings the stack up in demo mode (fixture weather, no live METAR, no keys),
# runs scripts/compose_smoke.py (catalog against frontend/src/lib/types.ts,
# golden path over HTTP), then the Playwright suite in frontend/e2e in a real
# browser, and always tears the stack down, volumes included.
#
#   scripts/e2e.sh            # needs docker compose, node, and once:
#                             #   (cd frontend && npx playwright install chromium)
#   E2E_KEEP=1 scripts/e2e.sh # leave the stack up afterwards
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
project="${E2E_PROJECT:-suas-e2e}"
compose=(docker compose --project-directory "$root" -p "$project")

teardown() {
  if [[ "${E2E_KEEP:-}" != "1" ]]; then
    "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap teardown EXIT

export DEMO_MODE=true
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-e2e-only-password}"
"${compose[@]}" up --build --detach --wait

python3 "$root/scripts/compose_smoke.py"
(cd "$root/frontend" && npx playwright test)
