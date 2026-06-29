# Startup Protocol — Solution Acceleration Engine

## Every time you open this Codespace on `main`

Execute these **3 commands** in the terminal, in order:

```bash
# 1 — Sync to the latest merged state
git pull origin main

# 2 — Clear any stale port bindings from a previous session
fuser -k 8000/tcp && fuser -k 3000/tcp && fuser -k 8001/tcp

# 3 — Start the unified orchestrator (Reflex frontend + state backend)
#     The FastAPI API is already running — started automatically by the
#     devcontainer `postStartCommand` (scripts/dev-start.sh).
python -m reflex run
```

**That's it.** The browser tab will open automatically at `http://localhost:3000`.

---

## What each step does

| Step | What it does |
|------|-------------|
| `git pull origin main` | Picks up any PRs you merged on GitHub before opening the Codespace |
| `fuser -k …` | Kills any lingering processes that survived a previous session (prevents EADDRINUSE errors) |
| `python -m reflex run` | Starts the Next.js frontend on **:3000** and the Reflex WebSocket state backend on **:8001**. The FastAPI API on **:8000** is already up (started by the devcontainer) |

---

## Service URLs

| Service | URL |
|---------|-----|
| Frontend (UI) | `http://localhost:3000` |
| REST API | `http://localhost:8000/api/health` |
| API Docs (Swagger) | `http://localhost:8000/docs` |

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
fuser -k 8000/tcp && fuser -k 3000/tcp && fuser -k 8001/tcp
```

### API not responding

```bash
tail -f /tmp/contexta-api.log
```

### Reflex WebSocket stuck "Pending"

This was fixed in PR #30. Ensure `rxconfig.py` derives `api_url` from
`CODESPACE_NAME` (auto-injected by Codespaces). If you see it locally,
run with:

```bash
REFLEX_API_URL=http://localhost:8001 python -m reflex run
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
