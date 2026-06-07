#!/usr/bin/env node
// Record two demo clips of the /monitor page driving a fake-DAQ run (issue #72):
//   out/clip1-run.mp4  (20s) — 17 tests stream in, failures get LLM-diagnosed,
//                              per-FEMB summaries stream to completion
//   out/clip2-chat.mp4 (10s) — "What has failed?" asked in the session chat
//
// One continuous headed-Chromium take, then ffmpeg cuts + uniform speedup +
// a 2s end-freeze per clip. See README.md for preconditions.

import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const FRONTEND = process.env.DEMO_FRONTEND || 'http://localhost:5173'
const BACKEND = process.env.DEMO_BACKEND || 'http://localhost:8000'
const OLLAMA = process.env.DEMO_OLLAMA || 'http://localhost:11434'

const OUT_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), 'out')
const CLIP1_BODY_S = 18 // sped-up run footage; +2s freeze = 20s
const CLIP2_BODY_S = 8 // sped-up chat footage; +2s freeze = 10s
const FREEZE_S = 2
const RUN_TIMEOUT_MS = 180_000 // hard cap on the fake-DAQ run + summaries
const CHAT_TIMEOUT_MS = 120_000
const CHAT_QUESTION = 'What has failed?'

async function mustReach(name, url) {
  try {
    const resp = await fetch(url)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  } catch (e) {
    console.error(`precondition failed: ${name} unreachable at ${url} (${e.message})`)
    process.exit(1)
  }
}

function cutClip(master, startS, endS, bodyTargetS, outFile) {
  const f = Math.max((endS - startS) / bodyTargetS, 0.01)
  execFileSync(
    'ffmpeg',
    [
      '-y', '-i', master,
      '-vf',
      `trim=start=${startS.toFixed(3)}:end=${endS.toFixed(3)},` +
        `setpts=(PTS-STARTPTS)/${f.toFixed(4)},fps=30,` +
        `tpad=stop_mode=clone:stop_duration=${FREEZE_S}`,
      '-an', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p',
      '-movflags', '+faststart',
      outFile,
    ],
    { stdio: ['ignore', 'ignore', 'inherit'] },
  )
  console.log(`wrote ${outFile} (${bodyTargetS + FREEZE_S}s, speedup ${f.toFixed(2)}x)`)
}

// --- preconditions: fail fast, never orchestrate the stack ---
await mustReach('backend', `${BACKEND}/monitor/config`)
await mustReach('frontend', FRONTEND)
await mustReach('ollama', `${OLLAMA}/api/tags`)
try {
  execFileSync('ffmpeg', ['-version'], { stdio: 'ignore' })
} catch {
  console.error('precondition failed: ffmpeg not on PATH')
  process.exit(1)
}

// Force local mode so a take can never hit the remote.
{
  const resp = await fetch(`${BACKEND}/monitor/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: 'local' }),
  })
  if (!resp.ok) {
    console.error(`failed to set local mode: HTTP ${resp.status}`)
    process.exit(1)
  }
}

fs.mkdirSync(OUT_DIR, { recursive: true })
const browser = await chromium.launch({ headless: false })
const context = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  recordVideo: { dir: OUT_DIR, size: { width: 1920, height: 1080 } },
})
const page = await context.newPage()
const t0 = Date.now() // recording starts with the page; marks are video offsets
const sec = () => (Date.now() - t0) / 1000

let clip1End, chatStart, chatEnd
try {
  await page.goto(`${FRONTEND}/monitor`)
  await page.waitForSelector('.monitor-topbar')

  // Kick off the fake DAQ run; the session tree self-refreshes ~3s later.
  await page.click('button.mock-daq')
  await page.waitForTimeout(4000)

  // Pick the newest run (rows are listed newest-first).
  await page.click('.picker-trigger')
  await page.waitForSelector('.picker-panel')
  if (!(await page.$('.picker-panel .run-row'))) {
    await page.click('.picker-panel .refresh-btn')
    await page.waitForSelector('.picker-panel .run-row', { timeout: 10_000 })
  }
  await page.click('.picker-panel .run-row')

  // Collapse the session chat so the timeline gets full width for clip 1.
  // (The collapse button only renders once a session is selected.)
  await page.click('button[title="Collapse chat panel"]')
  await page.waitForSelector('.rail-expand-btn')

  // Watch until every FEMB column has a finished summary and no diagnostic is
  // pending/streaming; keep the newest activity scrolled into view meanwhile.
  const deadline = Date.now() + RUN_TIMEOUT_MS
  for (;;) {
    const done = await page.evaluate(() => {
      const center = document.querySelector('.monitor-center')
      if (center) center.scrollTo({ top: center.scrollHeight, behavior: 'smooth' })
      const cols = document.querySelectorAll('.femb-cols > *').length
      const summaries = document.querySelectorAll('.summary-card').length
      const busy = document.querySelectorAll(
        '.summary-status.streaming, .diag-status.streaming, .diag-status.pending',
      ).length
      return cols > 0 && summaries === cols && busy === 0
    })
    if (done) break
    if (Date.now() > deadline) throw new Error('timed out waiting for the run + summaries to finish')
    await page.waitForTimeout(1000)
  }
  await page.waitForTimeout(1500) // settle on the finished report
  clip1End = sec()

  // Clip 2: reopen the chat and ask about the run we just watched.
  chatStart = sec()
  await page.click('.rail-expand-btn')
  const textarea = page.locator('.composer textarea')
  await textarea.waitFor()
  await textarea.pressSequentially(CHAT_QUESTION, { delay: 70 })
  await textarea.press('Enter')
  await page.waitForSelector('.composer textarea[disabled]', { timeout: 30_000 })
  await page.waitForSelector('.composer textarea:not([disabled])', { timeout: CHAT_TIMEOUT_MS })
  await page.waitForTimeout(1500) // settle on the finished answer
  chatEnd = sec()
} catch (e) {
  await context.close()
  await browser.close()
  console.error(`take failed: ${e.message}`)
  console.error(`raw footage (if any) is under ${OUT_DIR} for inspection`)
  process.exit(1)
}

const video = page.video()
await context.close() // flushes the recording
await browser.close()
const master = path.join(OUT_DIR, 'master.webm')
fs.renameSync(await video.path(), master)
console.log(`master take: ${master} (${chatEnd.toFixed(1)}s)`)

cutClip(master, 0, clip1End, CLIP1_BODY_S, path.join(OUT_DIR, 'clip1-run.mp4'))
cutClip(master, Math.max(chatStart - 1, 0), chatEnd, CLIP2_BODY_S, path.join(OUT_DIR, 'clip2-chat.mp4'))
console.log('done — re-run for another take if the random failures look off')
