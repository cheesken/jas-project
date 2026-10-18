// UI acceptance test for US-F-09: a result card shows the excerpt, source file
// name, source type, date and relevance score. Drives the real Electron app.
//
// Needs the backend running (docker compose up -d). Starts the Vite dev server
// itself unless one is already on :5173. Uploads its own uniquely named note
// (under your home folder, which the API can read), searches for it, checks
// the card, then deletes the note from the index.
//
//   cd frontend && npm run test:e2e
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { _electron as electron } from 'playwright';
import { createServer } from 'vite';

const API = (process.env.API_URL || 'http://localhost:8000').replace(/\/$/, '');
const WORK_DIR = process.env.E2E_DIR || path.join(os.homedir(), '.jas-acceptance');
const APP_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE_TYPES = ['Document', 'Browser History', 'Image'];
const DATE_LINE = /^(Modified|Visited|Captured): [A-Z][a-z]{2} \d{2}, \d{4}$/;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function ingest(filePath) {
  const res = await fetch(`${API}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_path: filePath, file_type: 'txt' }),
  });
  const body = await res.text();
  assert.equal(res.status, 201, body);
  const { job_id: jobId } = JSON.parse(body);
  for (let i = 0; i < 120; i++) {
    const status = await (await fetch(`${API}/ingest/${jobId}`)).json();
    if (status.status === 'COMPLETED') return jobId;
    assert.notEqual(status.status, 'FAILED', JSON.stringify(status));
    await sleep(1000);
  }
  throw new Error('note was not indexed within 120 s');
}

async function viteRunning() {
  try {
    return (await fetch('http://localhost:5173')).ok;
  } catch {
    return false;
  }
}

const run = randomUUID().slice(0, 8);
const folder = path.join(WORK_DIR, `ui-${run}`);
const fileName = `harbor_tip_${run}.txt`;
let jobId;
let vite;
let app;

try {
  if (!(await (await fetch(`${API}/health`)).ok)) throw new Error(`API not healthy at ${API}`);

  mkdirSync(folder, { recursive: true });
  const filePath = path.join(folder, fileName);
  writeFileSync(filePath, `Quentin Ashby recommended Harbor Lantern Cafe in Monterey for clam chowder. Ref ${run}.\n`);
  jobId = await ingest(filePath);

  if (!(await viteRunning())) {
    vite = await createServer({ root: APP_DIR, server: { port: 5173, strictPort: true }, logLevel: 'error' });
    await vite.listen();
  }

  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  env.JAS_SKIP_ONBOARDING = '1';
  app = await electron.launch({ args: ['.'], cwd: APP_DIR, env });
  const page = await app.firstWindow();
  await page.waitForSelector('text=Hello, there.');

  const search = page.locator('input').first();
  await search.fill('Which cafe did Quentin Ashby recommend?');
  await search.press('Enter');
  await page.waitForSelector('[data-testid="result-card"]', { timeout: 180_000 });

  const cards = await page.$$eval('[data-testid="result-card"]', (els) => els.map((el) => {
    const text = (id) => el.querySelector(`[data-testid="${id}"]`)?.textContent.trim() ?? '';
    return {
      source: text('result-source'), score: text('result-score'), file: text('result-file'),
      excerpt: text('result-excerpt'), date: text('result-date'),
    };
  }));
  assert.ok(cards.length >= 1 && cards.length <= 10, `expected 1-10 cards, got ${cards.length}`);
  for (const c of cards) {
    assert.ok(SOURCE_TYPES.includes(c.source), `source type badge: ${c.source}`);
    assert.match(c.score, /^Score: \d\.\d{2}$/);
    assert.ok(c.file.length > 0, 'file name');
    assert.ok(c.excerpt.length > 0, 'excerpt');
    assert.match(c.date, DATE_LINE);
  }
  const ours = cards.find((c) => c.file === fileName);
  assert.ok(ours, `uploaded note not among cards: ${cards.map((c) => c.file).join(', ')}`);
  assert.equal(ours.source, 'Document');
  assert.match(ours.excerpt, /Harbor Lantern Cafe/);
  assert.match(ours.date, /^Modified: /);

  mkdirSync(path.join(APP_DIR, 'e2e', 'artifacts'), { recursive: true });
  await page.screenshot({ path: path.join(APP_DIR, 'e2e', 'artifacts', 'result-cards.png') });
  console.log(`PASS US-F-09: ${cards.length} cards, all five fields shown; uploaded note ranked #${cards.indexOf(ours) + 1}`);
} catch (err) {
  console.error(`FAIL US-F-09: ${err.message}`);
  process.exitCode = 1;
} finally {
  if (app) await app.close();
  if (vite) await vite.close();
  if (jobId) await fetch(`${API}/ingest/${jobId}`, { method: 'DELETE' }).catch(() => {});
  rmSync(folder, { recursive: true, force: true });
}
