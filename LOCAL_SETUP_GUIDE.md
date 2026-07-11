# Local Setup Guide
## Solution Acceleration Engine — Mac (Intel + Apple Silicon)

> **Python 3.11 or 3.12 required.**
> Python 3.13+ introduces breaking changes in several upstream packages.
> Python 3.14 is experimental and not supported.

---

## What you'll end up with

```
Terminal 1 — Headroom proxy  (port 8787)   keeps LLM costs low via semantic caching
Terminal 2 — SAE app         (port 8000)   Reflex UI + FastAPI backend + SQLite DB
```

All LLM traffic (Groq, OpenRouter, Gemini) passes through the Headroom proxy on
port 8787 before reaching the cloud.  Identical or semantically similar prompts are
served from cache — saving 50–90 % of tokens in typical review workflows.

---

## Prerequisites — do this once

### 1 · Xcode Command Line Tools

```bash
xcode-select --install
```

Already installed? You'll see `error: command line tools are already installed` — that's fine.

### 2 · Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

On Apple Silicon, follow the post-install instructions to add `/opt/homebrew/bin` to your PATH.

### 3 · Python 3.11 or 3.12

```bash
brew install python@3.11
python3.11 --version   # expected: Python 3.11.x
```

> Use `python@3.12` if you prefer 3.12 — both are fully supported.
> Do **not** use the system Python (`/usr/bin/python3`) or Python 3.13+.

### 4 · Git

```bash
brew install git
```

### 5 · Headroom AI proxy

```bash
brew install headroomlabs-ai/tap/headroom
headroom --version     # expected: 0.31.0 or higher
headroom init          # first-time setup; follow any on-screen prompts
```

> If the tap formula isn't available yet, check the latest install method at
> https://github.com/headroomlabs-ai/headroom

### 6 · Clone the repo

```bash
git clone https://github.com/LoneWolfDen/Solution-Acceleration-Engine.git
cd Solution-Acceleration-Engine
```

All commands below assume your terminal is inside the `Solution-Acceleration-Engine`
directory.

---

## One-time environment setup

Run these steps once.  After the first run, only the two `source` activation
commands are needed at the start of each new session.

### Step 1 — Raise the file-descriptor limit

Reflex's frontend compiler reads thousands of `node_modules` files in parallel.
Without this, the build crashes with `EMFILE: too many open files`.

```bash
ulimit -n 65536
```

**Make it permanent (recommended):**

```bash
echo 'ulimit -n 65536' >> ~/.zshrc && source ~/.zshrc
```

### Step 2 — Create the virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Your prompt will change to `(.venv) …` — all subsequent commands run inside
this environment.

### Step 3 — Install dependencies

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

Takes 1–3 minutes on the first run.  Verify critical packages afterwards:

```bash
pip show reflex fastapi aiosqlite litellm
```

### Step 4 — Build the `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in your values.  The minimum required set:

```bash
# At least one LLM key:
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Headroom proxy routing (route ALL LLM calls through port 8787):
OPENAI_BASE_URL=http://localhost:8787/v1
ANTHROPIC_BASE_URL=http://localhost:8787
```

> `OPENAI_BASE_URL` and `ANTHROPIC_BASE_URL` **must** be set to the Headroom
> proxy address — this is how LiteLLM intercepts every outbound LLM call
> regardless of provider.  Leave them as-is; do not change the paths.

The database path defaults to `contexta.db` in the project root — no override
needed for local dev.  See `.env.example` for Docker and custom path options.

### Step 5 — Initialise the database

```bash
python scripts/init_db.py
```

Expected output:

```
INFO  Target database: /path/to/Solution-Acceleration-Engine/contexta.db
INFO  Database migrated to schema version 5.
INFO  Database initialised successfully.
INFO  Tables present (15): alembic_version, app_config, artifact_version_links,
      artifacts, global_client_insights, intelligence_layer, ...
INFO  All expected tables are present. Database is ready.
```

This script is **idempotent** — safe to run again at any time without side effects.

### Step 6 — Initialise Reflex

```bash
reflex init
```

This creates `.web/` and downloads the frontend toolchain (bun + node_modules).
Takes 2–5 minutes on the first run; much faster afterwards.

---

## Running the app — every session

Open **two terminal tabs**.

### Terminal 1 — Headroom proxy (keep this running)

```bash
ulimit -n 65536
source .venv/bin/activate
headroom proxy --port 8787
```

Expected output:

```
╔══════════════════════════════════════════╗
║  Headroom Proxy  v0.31.0                 ║
║  Listening on http://127.0.0.1:8787      ║
║  Semantic cache: ENABLED                 ║
╚══════════════════════════════════════════╝
```

**Leave this tab alone.**  Every LLM call logs here.
Cache hits appear as `[CACHE HIT]`; first-call misses appear as `[PROXY]`.

### Terminal 2 — SAE application

```bash
ulimit -n 65536
source .venv/bin/activate

# Load your .env variables into the shell:
export $(grep -v '^#' .env | grep -v '^$' | xargs)

# Verify proxy routing is active:
echo $OPENAI_BASE_URL    # expected: http://localhost:8787/v1

# Start the app:
python -m reflex run --env dev --backend-port 8000
```

First start downloads the JavaScript bundler and installs frontend packages
(2–5 minutes).  Subsequent starts take under 30 seconds.

Watch for:

```
─────────────────────────────────────── App Running ───────────────────────────────────────
 URL: http://localhost:3000
```

**Open http://localhost:3000 in your browser.**

> In dev mode Reflex uses two ports:
> - `:3000` — Next.js frontend with hot-reload
> - `:8000` — FastAPI backend + Reflex WebSocket
>
> Always use `:3000` in dev mode.  Production (`--env prod`) uses `:8000` only.

---

## Verify it's working

### Health check

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

```json
{
    "status": "ok",
    "version": "0.1.0",
    "error": null
}
```

### First project

1. Open http://localhost:3000
2. Click **"New Project"** in the left sidebar
3. Enter a name and click **"Create"**
4. The project appears in the sidebar within 1–2 seconds — no error toast

### Admin panel

Open http://localhost:3000/admin.

Enter your API key for one provider and click **Save Key**.
The status indicator changes from `not_set` to `set`.

### Headroom cache hit

After running one review, run it again with identical settings.
In Terminal 1 you should see `[CACHE HIT]` instead of `[PROXY]`.

Check cumulative savings at any time:

```bash
headroom savings
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `EMFILE: too many open files` | File-descriptor limit too low | `ulimit -n 65536` in every terminal tab |
| `ModuleNotFoundError: No module named 'reflex'` | venv not active | `source .venv/bin/activate` |
| `AttributeError: 'State' object has no attribute 'db'` | Old stale `.pyc` cache | `find . -name '*.pyc' -delete && python -m reflex run …` |
| `Connection refused` on port 3000 or 8000 | App not started | Wait for `App Running` in Terminal 2 |
| `Connection refused` on port 8787 | Headroom proxy not running | Start it: `headroom proxy --port 8787` |
| LLM calls return `502` or `Connection refused` | Proxy up, but key missing | Add key to `.env` and re-export |
| Blank white screen | Frontend build failed | Check Terminal 2 for JS errors; re-run `python -m reflex run …` |
| Tables missing on fresh launch | DB not initialised | `python scripts/init_db.py` |
| `error: externally-managed-environment` | Using system pip | `source .venv/bin/activate` first |
| WebSocket stuck as "Pending" | `api_url` wrong | Add `REFLEX_API_URL=http://localhost:8000` to `.env` and re-export |

### Full reset

```bash
# Stop all running processes (Ctrl+C in each terminal tab), then:
rm -rf .venv .web contexta.db

python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
python scripts/init_db.py
reflex init
python -m reflex run --env dev --backend-port 8000
```

---

## Cheat sheet

```
Every session — run in each new terminal tab first:
  ulimit -n 65536
  source .venv/bin/activate

Tab 1 (proxy — leave running):
  headroom proxy --port 8787

Tab 2 (app):
  export $(grep -v '^#' .env | grep -v '^$' | xargs)
  python -m reflex run --env dev --backend-port 8000

Browser:
  http://localhost:3000
```

---

*Guide updated for SAE v0.1.0 · Reflex ≥ 0.9.6 · Python 3.11/3.12 · Headroom ≥ 0.31.0*
