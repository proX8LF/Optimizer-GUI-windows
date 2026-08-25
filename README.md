# Optimizer GUI

Next.js frontend + Python (FastAPI) backend, packaged into a single Windows `.exe` via Tauri.
macOS/iOS-style dashboard. 37 real optimizations across 6 categories (Process Control, Power &
CPU, Network, System & UI, Storage, Advanced), all driven by one schema (`MENU` in
`backend/main.py`) so the UI renders itself — add a new action by adding one entry to `MENU`
and `ACTIONS`, no frontend changes needed.

## Project layout

```
backend/        FastAPI server (source of truth for every optimization + the UI schema)
frontend/       Next.js dashboard (static export, consumed by Tauri)
src-tauri/      Rust shell - bundles frontend + Python sidecar into optimizer.exe
.github/workflows/build-windows.yml   Builds the full exe on a real Windows runner
```

## Get the EXE (no local Windows build needed)

1. Push this folder to a GitHub repo:
   ```bash
   git init
   git add .
   git commit -m "initial commit"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```
2. Go to your repo's **Actions** tab → open the running workflow → wait for it to finish
   (~5-8 minutes: builds frontend, freezes Python, compiles Rust, bundles everything).
3. Download `optimizer-gui-windows` from the **Artifacts** section at the bottom of the run.
   It contains `optimizer.exe` (NSIS installer) and/or `.msi`.

For a permanent link on your repo's **Releases** page instead:
```bash
git tag v1.0.0
git push origin v1.0.0
```

No token needed — `GITHUB_TOKEN` is auto-provided by GitHub Actions, scoped to your own repo.

## Run it

Install/run as Administrator — most options (affinity, priority, registry/service changes)
are denied without elevation. The app opens a single window; the Python backend starts and
stops automatically with it.

## Local development (optional, needs Windows + Rust + Node + Python)

```bash
cd backend && pip install -r requirements.txt && python main.py
```
In a second terminal:
```bash
cd frontend && npm install && npm run dev
```
Then, in a third terminal, from `src-tauri`: `tauri dev` (requires `cargo install tauri-cli`,
or `npx @tauri-apps/cli dev` from the repo root).
