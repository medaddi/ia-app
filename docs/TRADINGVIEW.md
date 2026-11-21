# TradingView Advanced Charts in the app

The chart page and the 4-chart grid use **TradingView Advanced Charts (Charting Library)** as soon as the library's files
are served at `/charting_library/`. Until then the app's own chart (Lightweight Charts) shows; nothing else changes.

## What the integration does

- **Prices:** the library ships no market data. Its datafeed (`frontend/src/tradingview/datafeed.ts`) reads the app's own
  candles (`/api/exunu/candles`), the same feed every pair agent decides on, and polls the forming candle every 2 s.
  So the chart shows exactly the prices behind each signal.
- **Analysis:** each pair's agent overlay is drawn as TradingView objects (`frontend/src/tradingview/TradingViewChart.tsx`):
  zones → rectangles, levels (the channel high / low, the broken level) → lines, signals → `BREAKOUT` / `FADE` arrows, the
  running trade → a long / short position tool with its stop and its 2R target. EMA 50 / 200 are added as studies.
- **All 4 pairs**, on each agent's timeframe (H1, GBP/USD H4); the timeframe buttons of the library and the app stay in step.

## Getting the library (TradingView's licence)

1. Request access at <https://www.tradingview.com/advanced-charts/> (free for a public web app; TradingView reviews the request).
2. Once approved, TradingView gives your GitHub account access to its private `charting_library` repository.
3. Copy its `charting_library/` folder (and `datafeeds/` if you like) into `frontend/public/`:

   ```text
   frontend/public/charting_library/charting_library.standalone.js
   frontend/public/charting_library/bundles/…
   ```

4. Run the app: the chart page switches to TradingView by itself.

## Deploying (read this before pushing)

The licence forbids publishing the library in a **public** repository, and `medaddi/ia-app` is public. So
`frontend/public/charting_library/` is in `.gitignore`. To have it in production:

- make the GitHub repository **private** (GitHub → Settings → General → Danger zone → Change visibility), then remove the
  two `charting_library` / `datafeeds` lines from `.gitignore`, commit the folder and push: Vercel builds it in; or
- keep the repo public and upload the built frontend with the library some other way (for example `vercel deploy` from a
  machine that has the folder).

Without the folder in production, the live site keeps the app's own chart.
