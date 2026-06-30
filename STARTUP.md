# Startup Protocol — Solution Acceleration Engine

## Every time you open this Codespace on `main`

Execute these **3 commands** in the terminal, in order:

```bash
# 1 — Sync to the latest merged state
git pull origin main

# 2 — Stop any services left over from a previous session
bash scripts/dev-start.sh stop

# 3 — Start all services: FastAPI API (:8000) + Reflex (:3000 / :8001)
bash scripts/dev-start.sh
```

**That's it.** The browser tab will open automatically at `http://localhost:3000`.

---

## What each step does

| Step | What it does |
|------|-------------|
| `git pull origin main` | Picks up any PRs you merged on GitHub before opening the Codespace |
| `bash scripts/dev-start.sh stop` | Cleanly kills any lingering API or Reflex processes from a previous session |
| `bash scripts/dev-start.sh` | Starts FastAPI on **:8000**, Reflex frontend on **:3000**, and Reflex WebSocket state-sync on **:8001** |

---

## Service URLs

| Service | URL |
|---------|-----|
| Frontend (UI) | `http://localhost:3000` |
| REST API | `http://localhost:8000/api/health` |
| API Docs (Swagger) | `http://localhost:8000/docs` |

---

## Tail logs after startup

```bash
tail -f /tmp/contexta-api.log      # FastAPI uvicorn
tail -f /tmp/contexta-reflex.log   # Reflex frontend + state backend
```

---

## Health check — verify all 18 API endpoints are reachable

```bash
bash scripts/healthcheck.sh
```

Expected output ends with `STATUS: ALL CHECKS PASSED ✓`.

---

## Docker (production) usage

```bash
# Build and run the full single-container deployment
docker compose up --build

# Check health
docker compose exec contexta bash scripts/healthcheck.sh
```

---

## If something goes wrong

### Port already in use (`EADDRINUSE`)

```bash
bash scripts/dev-start.sh stop
bash scripts/dev-start.sh
```

### API not responding

```bash
tail -f /tmp/contexta-api.log
```

### Reflex WebSocket stuck "Pending"

`rxconfig.py` derives `api_url` from `CODESPACE_NAME` (auto-injected by
Codespaces), pointing the frontend WebSocket at **:8001** instead of the
FastAPI port **:8000**.  If you see this issue running outside Codespaces,
set the environment variable explicitly before calling `dev-start.sh`:

```bash
export REFLEX_API_URL=http://localhost:8001
bash scripts/dev-start.sh
```

### `UntypedVarError` in `web/state.py`

All state vars must carry explicit Python type annotations. The rule:

- Use `list[dict]` for API collections (not `list[SomePydanticModel]`)
- Use `rx.len(state_var)` to get the length of a state list in components
- Use bracket notation for dict access: `state_var["key"]` not `state_var.key`

---

## Dependency conflicts / rebuild

If you see Pydantic v1/v2 conflicts or import errors after a `git pull`:

```bash
pip install -e ".[dev]"
```

This reinstalls all dependencies from `pyproject.toml` in a single pass,
ensuring version pins are respected.  **Do not** run manual `pip install`
commands for individual packages — update `pyproject.toml` instead and
re-run the above.
