#!/usr/bin/env bash
# healthcheck.sh — verify all Contexta API endpoints are mounted and reachable.
#
# Usage:
#   bash scripts/healthcheck.sh                  # default: http://localhost:8000
#   bash scripts/healthcheck.sh http://host:8000 # custom base URL
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed

set -uo pipefail

BASE="${1:-http://localhost:8000}"
PASS=0
FAIL=0
ERRORS=()

# ── helpers ───────────────────────────────────────────────────────────────────

check_http() {
    local label="$1"
    local url="$2"
    local expected="${3:-200}"
    local actual
    actual=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
    if [[ "$actual" == "$expected" ]]; then
        printf "  \033[32m✓\033[0m %s (%s)\n" "$label" "$actual"
        PASS=$((PASS + 1))
    else
        printf "  \033[31m✗\033[0m %s (expected %s, got %s)\n" "$label" "$expected" "$actual"
        FAIL=$((FAIL + 1))
        ERRORS+=("$label — expected HTTP $expected, got $actual")
    fi
}

check_route_in_spec() {
    local route="$1"
    local spec="$2"
    if echo "$spec" | python3 -c "
import sys, json
spec = json.load(sys.stdin)
paths = list(spec.get('paths', {}).keys())
route = sys.argv[1]
sys.exit(0 if route in paths else 1)
" "$route" 2>/dev/null; then
        printf "  \033[32m✓\033[0m route registered: %s\n" "$route"
        PASS=$((PASS + 1))
    else
        printf "  \033[31m✗\033[0m route MISSING from spec: %s\n" "$route"
        FAIL=$((FAIL + 1))
        ERRORS+=("Route not in OpenAPI spec: $route")
    fi
}

# ── section 1: liveness ───────────────────────────────────────────────────────

echo ""
echo "=== Contexta API Health Check ==="
printf "    Base: %s\n\n" "$BASE"

echo "[1/3] Liveness probe"
check_http "GET /api/health" "$BASE/api/health"

# ── section 2: stateless GET endpoints ───────────────────────────────────────

echo ""
echo "[2/3] Stateless GET endpoints (no ID required)"
check_http "GET /api/projects"              "$BASE/api/projects"
check_http "GET /api/artifacts/suggestions" "$BASE/api/artifacts/suggestions"
check_http "GET /api/admin/health"          "$BASE/api/admin/health"
check_http "GET /api/admin/config"          "$BASE/api/admin/config"

# ── section 3: OpenAPI route registration ────────────────────────────────────

echo ""
echo "[3/3] Route registration (OpenAPI spec)"

SPEC_JSON=$(curl -s --max-time 10 "$BASE/openapi.json" 2>/dev/null || echo "")

if [[ -z "$SPEC_JSON" ]]; then
    printf "  \033[31m✗\033[0m Could not fetch /openapi.json\n"
    FAIL=$((FAIL + 1))
    ERRORS+=("OpenAPI spec: fetch failed — is the API running?")
else
    printf "  \033[32m✓\033[0m /openapi.json fetched\n"
    PASS=$((PASS + 1))

    # All 21 registered routes (confirmed via contexta/api/ router files)
    ROUTES=(
        "/api/health"
        "/api/projects"
        "/api/projects/{project_id}"
        "/api/projects/{project_id}/versions"
        "/api/projects/{project_id}/artifacts"
        "/api/versions"
        "/api/versions/{version_id}"
        "/api/versions/{version_id}/reviews"
        "/api/artifacts"
        "/api/artifacts/{artifact_id}"
        "/api/artifacts/suggestions"
        "/api/nodes/{node_id}"
        "/api/reviews"
        "/api/reviews/{review_id}/status"
        "/api/proposals"
        "/api/proposals/{proposal_id}/status"
        "/api/admin/health"
        "/api/admin/config"
    )

    for route in "${ROUTES[@]}"; do
        echo "$SPEC_JSON" | check_route_in_spec "$route" /dev/stdin
    done
fi

# ── summary ───────────────────────────────────────────────────────────────────

echo ""
echo "=================================="
printf "  Passed : %d\n" "$PASS"
printf "  Failed : %d\n" "$FAIL"

if [[ ${#ERRORS[@]} -gt 0 ]]; then
    echo ""
    echo "  Failures:"
    for err in "${ERRORS[@]}"; do
        printf "    • %s\n" "$err"
    done
fi

echo ""
if [[ $FAIL -eq 0 ]]; then
    printf "  \033[32mSTATUS: ALL CHECKS PASSED ✓\033[0m\n\n"
    exit 0
else
    printf "  \033[31mSTATUS: %d CHECK(S) FAILED ✗\033[0m\n\n" "$FAIL"
    exit 1
fi
