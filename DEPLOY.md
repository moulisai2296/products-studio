# PhotoDukaan — Deploy & Ops

Two services: **backend** (FastAPI on Render) and **frontend** (Next.js on Vercel),
plus **Supabase** (Postgres) and optional **Drive** + **Langfuse**.

## 0. Local run
```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
cp .env.example .env            # fill in keys; MOCK_MODE=1 needs nothing
.venv/Scripts/python -m uvicorn main:app --reload --port 8000

# frontend
cd frontend
npm install
echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local
npm run dev                     # http://localhost:3000/studio
```
`MOCK_MODE=1` runs the whole app with zero external deps. Flip to `0` for real APIs.

## 1. Supabase (persistence)
Tables `sessions` + `assets` are created. To (re)create or upgrade columns:
```bash
# Option A: add SUPABASE_DB_PASSWORD to backend/.env, then:
cd backend && python setup_db.py
# Option B: paste backend/schema.sql into the Supabase SQL Editor (idempotent)
```
The app runs fine even if Supabase is down — it falls back to an in-memory store.

## 2. Backend on Render
- New → Blueprint → pick this repo (`render.yaml` is at the root; `rootDir: backend`).
- Set the `sync:false` env vars in the Render dashboard (see list below).
- Health check: `/api/health`. Start command uses gunicorn + uvicorn workers.
- After first deploy, set `PUBLIC_BASE_URL` to the service URL
  (e.g. `https://photodukaan-api.onrender.com`) and redeploy — asset URLs are
  built from it.

> Note: Render's free disk is ephemeral. Generated images/reels under
> `static/assets/` are also mirrored to Supabase (metadata) and Google Drive
> (files), so a restart loses only local copies, not the campaign record.

## 3. Frontend on Vercel
- New Project → import repo → **Root Directory: `frontend`** (framework auto-detected).
- Env var: `NEXT_PUBLIC_API_BASE = https://<your-render-service>.onrender.com`
- Deploy. Then set the backend's `ALLOWED_ORIGINS` to the Vercel URL and redeploy backend.

## 4. Env vars (backend)
| Var | Needed for | Notes |
|---|---|---|
| `MOCK_MODE` | core | `0` for real APIs, `1` for mock demo |
| `DEMO_FALLBACK` | insurance | `1` serves seed/ assets if venue network dies |
| `GEMINI_API_KEY` | images/reel | Google AI Studio key |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | persistence | service (secret) key, backend only |
| `SUPABASE_DB_PASSWORD` | table setup only | only for `setup_db.py`, not runtime |
| `DRIVE_PARENT_FOLDER_ID` / `GOOGLE_SERVICE_ACCOUNT_JSON` | Drive sync | JSON inline or file path |
| `LANGFUSE_ENABLED` + `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | observability | `0` cleanly no-ops |
| `PUBLIC_BASE_URL` | asset URLs | this backend's public URL |
| `ALLOWED_ORIGINS` | CORS | your Vercel URL in prod (`*` for dev) |

## 5. Tests
```bash
cd backend && .venv/Scripts/python -m pytest tests/ -q
```
