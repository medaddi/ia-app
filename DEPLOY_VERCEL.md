# Deploy EXUNU on Vercel

This repository deploys as two Vercel projects that share the same Git repository:

| Project | Vercel root directory | Production URL |
| --- | --- | --- |
| Backend | `backend` | `https://ia-app-tawny.vercel.app` |
| Frontend | `frontend` | `https://ia-app-co94.vercel.app` |

## 1. Create a persistent database

In Vercel, open the **backend project → Storage/Marketplace → Neon → Install**, select the Free plan if available, choose a nearby region, and connect the database to the backend project. Marketplace integrations can inject their connection variables into the project. The backend reads `DATABASE_URL` or `POSTGRES_URL`; use a pooled connection URL for serverless traffic (Neon URLs with `-pooler` and `sslmode=require`). If no variable was injected, add the pooled connection string as `DATABASE_URL` in the backend project's Production environment, then redeploy. Vercel's function filesystem is temporary, so do not use SQLite for deployed data.

The app creates its tables from `backend/app/models.py` on first startup and safely serializes schema setup if Vercel starts multiple functions at once. Do not import the root `database_schema.sql`: it is a legacy MySQL schema from an older version and does not match this backend. The local `backend/data/exunu.db` is not uploaded or migrated automatically.

## 2. Configure and deploy the backend

Create a Vercel project from this repository and set its Root Directory to `backend`. Keep the included `backend/vercel.json`; the Python app is served at the project root, so routes such as `/api/health` and `/api/auth/login` remain available.

Add these Production environment variables to the backend project:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Hosted PostgreSQL connection URL |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_ACCESS_CODE` | `admin1234` |
| `CORS_ORIGINS` | `https://ia-app-co94.vercel.app` |
| `CRON_SECRET` | A long, random secret used by the scheduler request |
| `SCHEDULER_ENABLED` | `false` |
| `TELEGRAM_POLLING` | `false` |

Use `https://ia-app-tawny.vercel.app` as the Production Domain. On an empty database, the app creates the admin account from `ADMIN_USERNAME` and `ADMIN_ACCESS_CODE`. If the configured admin row already exists with an older password hash, signing in with `admin1234` updates that row's stored hash.

After deploying, `https://ia-app-tawny.vercel.app/api/health` should return JSON with `"status":"ok"` and `"database":"ok"`. This confirms the API can reach PostgreSQL. To confirm writes persist, create a test user or trade in the app, reload it, and confirm the record remains.

## 3. Configure and deploy the frontend

Create a second Vercel project from the same repository and set its Root Directory to `frontend`. Use the detected Vite settings (`npm run build`, output directory `dist`) and set:

| Variable | Value |
| --- | --- |
| `VITE_API_URL` | `https://ia-app-tawny.vercel.app` |

Use `https://ia-app-co94.vercel.app` as the frontend Production Domain, then redeploy so the API URL is included in the frontend build.

## 4. Keep automatic signals running

Vercel functions do not keep the in-process candle scheduler alive. The backend exposes a protected one-pass endpoint for an external scheduler:

```text
GET https://ia-app-tawny.vercel.app/api/cron/tick
Authorization: Bearer <the CRON_SECRET value>
```

Set an external scheduler to call it every minute, with the `Authorization` header above. Vercel Hobby Cron currently permits only one run per day, which is too slow for the app's M5/M15 signal checks. Calls without the correct secret are rejected.

## 5. Optional Telegram bot commands

To make Telegram commands work on Vercel, also add these backend Production variables:

| Variable | Value |
| --- | --- |
| `TELEGRAM_WEBHOOK_URL` | `https://ia-app-tawny.vercel.app/api/telegram/webhook` |
| `TELEGRAM_WEBHOOK_SECRET` | A random Telegram webhook secret using letters, numbers, `_` or `-` |

When an admin connects a bot in the app, the backend registers this webhook with Telegram. Automatic signal delivery still requires the external scheduler in step 4. Keep `TELEGRAM_POLLING=false` on Vercel.

## Login

On a fresh database, sign in with username `admin` and access code `admin1234`. This is the requested bootstrap credential; anyone who can reach the public login page can try it, so change it after the first login if the app will be shared publicly.
