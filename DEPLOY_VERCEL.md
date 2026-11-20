# Deploy LiquidityDissection on Vercel

This repository deploys as two Vercel projects that share the same Git repository:

| Project | Vercel root directory | Production URL |
| --- | --- | --- |
| Backend | `backend` | `https://ia-app-tawny.vercel.app` |
| Frontend | `frontend` | `https://liquiditydissection.app` (Vercel address: `https://ia-app-co94.vercel.app`) |

## 1. Create a persistent database

The app runs on a free **Supabase** Postgres database (project `liquiditydissection-db`, us-east-1, since 2026-11-20; it
replaced Neon, whose free quota ran out). It is connected with Supabase's Vercel integration (Supabase → Project Settings →
Integrations → Vercel → the backend project), which injects `POSTGRES_URL` and the other variables; no password is typed by
hand. The backend reads, in this order: `APP_DATABASE_URL`, `POSTGRES_URL`, `DATABASE_URL`, `DATABASE_POSTGRES_URL`
(`app/config.py`). Vercel's function filesystem is temporary, so never use SQLite for deployed data.

The app creates its tables from `backend/app/models.py` on startup, adds missing columns, and turns on Row Level Security on
every table (Supabase's public REST API then sees nothing; the app connects as the tables' owner and is not affected). The
local `backend/data/exunu.db` is never uploaded.

The old Neon data can be copied in once Neon accepts connections again: as admin, `POST /api/admin/import-old-db` counts
the rows (dry run), and `POST /api/admin/import-old-db?dry_run=false` replaces the active rows with the old ones.

## 2. Configure and deploy the backend

Create a Vercel project from this repository and set its Root Directory to `backend`. Keep the included `backend/vercel.json`; the Python app is served at the project root, so routes such as `/api/health` and `/api/auth/login` remain available.

Add these Production environment variables to the backend project:

| Variable | Value |
| --- | --- |
| `POSTGRES_URL` | set by the Supabase integration (section 1) |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_ACCESS_CODE` | a strong code of your own (the first admin's password on an empty database) |
| `CORS_ORIGINS` | `https://liquiditydissection.app` |
| `CRON_SECRET` | A long, random secret used by the scheduler request |
| `SCHEDULER_ENABLED` | `false` |
| `TELEGRAM_POLLING` | `false` |

Use `https://ia-app-tawny.vercel.app` as the Production Domain. On an empty database, the app creates the admin account from `ADMIN_USERNAME` and `ADMIN_ACCESS_CODE`.

After deploying, `https://ia-app-tawny.vercel.app/api/health` should return JSON with `"status":"ok"` and `"database":"ok"`. This confirms the API can reach PostgreSQL. To confirm writes persist, create a test user or trade in the app, reload it, and confirm the record remains.

## 3. Configure and deploy the frontend

Create a second Vercel project from the same repository and set its Root Directory to `frontend`. Use the detected Vite settings (`npm run build`, output directory `dist`) and set:

| Variable | Value |
| --- | --- |
| `VITE_API_URL` | `https://ia-app-tawny.vercel.app` |

Use `https://liquiditydissection.app` as the frontend Production Domain, then redeploy so the API URL is included in the frontend build.

## 4. Keep automatic signals running (Vercel Cron, Pro plan)

Vercel functions only run when called: nothing in the backend runs on its own between requests. Something must call the
one-pass endpoint **every minute**: at each call every pair's setup agent decides on the candle that just closed, its
trade-management agent follows the trades already sent, and a fresh setup goes to Telegram and to the app.

```text
GET https://ia-app-tawny.vercel.app/api/cron/tick
Authorization: Bearer <the CRON_SECRET value>
```

On **Vercel Pro** this is built in: `backend/vercel.json` declares the cron

```json
"crons": [{ "path": "/api/cron/tick", "schedule": "* * * * *" }]
```

1. In the **backend** project, set the Production variable `CRON_SECRET` (a long random string). Vercel sends it as
   `Authorization: Bearer <CRON_SECRET>` on every cron call; calls without it are rejected.
2. Redeploy the backend to Production (crons run on the production deployment only).
3. Check it: Project → Settings → Cron Jobs shows `/api/cron/tick` every minute, and `GET /api/cron/status` (or the
   dashboard's engine card) shows the last tick less than 3 minutes ago.
4. Function duration: a tick gives each pair up to 40 s (`TICK_TIMEOUT`); keep the function's max duration at 60 s or more
   (the Pro default with Fluid compute is enough).

A signal goes out within about a minute of the M5 candle close (the cron runs once a minute). On Hobby, Vercel Cron runs
once a day only: use an external scheduler there instead (any service that calls the URL above every minute with the header).

## 5. Optional Telegram bot commands

To make Telegram commands work on Vercel, also add these backend Production variables:

| Variable | Value |
| --- | --- |
| `TELEGRAM_WEBHOOK_URL` | `https://ia-app-tawny.vercel.app/api/telegram/webhook` |
| `TELEGRAM_WEBHOOK_SECRET` | A random Telegram webhook secret using letters, numbers, `_` or `-` |

When an admin connects a bot in the app, the backend registers this webhook with Telegram. Automatic signal delivery still requires the cron in step 4. Keep `TELEGRAM_POLLING=false` on Vercel.

## Login

On a fresh database, sign in with username `admin` and the value of `ADMIN_ACCESS_CODE`. Without that variable the code
falls back to a known default, so always set it in production.

## Telegram bot and phone notifications after a new database

The bot token, the linked Telegram chats and the phones' push subscriptions live in the database. On a new database:
paste the bot token again in the app (admin → Telegram), relink each Telegram with `/start`, and turn notifications on
again on each phone (the push keys are new).
