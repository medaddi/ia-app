# Deploy EXUNU on Vercel

This repository deploys as two Vercel projects that share the same Git repository:

| Project | Vercel root directory | Production URL |
| --- | --- | --- |
| Backend | `backend` | `https://ia-app-tawny.vercel.app` |
| Frontend | `frontend` | `https://ia-app-co94.vercel.app` |

## 1. Create a persistent database

Create a PostgreSQL database with Neon, Supabase, or another hosted provider. Copy its pooled or direct connection URL and add it to the **backend** Vercel project as `DATABASE_URL` for Production. Vercel's function filesystem is temporary, so do not use SQLite for deployed data.

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

Use `https://ia-app-tawny.vercel.app` as the Production Domain. On the first start against an empty database, the app creates the admin account from `ADMIN_USERNAME` and `ADMIN_ACCESS_CODE`. Existing accounts are kept; changing the environment variable does not reset an existing admin password.

After deploying, `https://ia-app-tawny.vercel.app/api/health` should return JSON with `"status":"ok"`.

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
