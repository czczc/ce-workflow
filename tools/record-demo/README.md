# record-demo

Records two demo clips of the `/monitor` page driving a local fake-DAQ run
(issue #72):

- `out/clip1-run.mp4` (20s) — 17 QC tests stream in, failed tests get
  auto-diagnosed by the local Ollama LLM, per-FEMB run summaries stream to
  completion. Uniform speedup + 2s end-freeze on the finished report.
- `out/clip2-chat.mp4` (10s) — "What has failed?" asked in the session chat
  right after the run; the answer streams in.

Both clips are cut from one continuous headed-Chromium take (`out/master.webm`),
so the chat genuinely answers about the run shown in clip 1.

## Preconditions

The script fails fast if any of these are not already running:

- backend on :8000 (`cd backend && uv run uvicorn main:app`)
- frontend on :5173 (`cd frontend && npm run dev`)
- Ollama on :11434 with `qwen3.5:4b` + `nomic-embed-text:v1.5` pulled
- Qdrant on :6333 (`cd docker && docker compose up -d`)
- `ffmpeg` on PATH

The script POSTs `{"mode": "local"}` to `/monitor/config` before recording, so
a take can never run against the remote.

## Usage

```bash
cd tools/record-demo
npm install
npx playwright install chromium   # one-time browser download
npm run record
```

A take runs ~1–2 minutes real-time (35s fake-DAQ drip + LLM generation).
Failures are random (1–3 per FEMB) — just re-run until you like the take.

Override endpoints with `DEMO_FRONTEND`, `DEMO_BACKEND`, `DEMO_OLLAMA` env vars.
