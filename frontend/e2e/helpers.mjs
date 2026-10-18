import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { _electron as electron } from 'playwright';
import { createServer } from 'vite';

export const API = (process.env.API_URL || 'http://localhost:8000').replace(/\/$/, '');
export const WORK_DIR = process.env.E2E_DIR || path.join(os.homedir(), '.jas-acceptance');
export const APP_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const ARTIFACTS = path.join(APP_DIR, 'e2e', 'artifacts');

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function getJSON(route) {
  const res = await fetch(`${API}${route}`);
  assert.ok(res.ok, `${route} returned ${res.status}`);
  return res.json();
}

export async function ingest(filePath, fileType, { expect = 'COMPLETED' } = {}) {
  const res = await fetch(`${API}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_path: filePath, file_type: fileType }),
  });
  const body = await res.text();
  assert.equal(res.status, 201, body);
  const { job_id: jobId } = JSON.parse(body);
  for (let i = 0; i < 120; i++) {
    const status = await getJSON(`/ingest/${jobId}`);
    if (status.status === expect) return jobId;
    if (status.status === 'COMPLETED' || status.status === 'FAILED') {
      assert.fail(`expected ${expect}, job ended ${status.status}: ${status.error_message}`);
    }
    await sleep(1000);
  }
  throw new Error(`${path.basename(filePath)} did not finish within 120 s`);
}

export async function forget(jobId) {
  if (jobId) await fetch(`${API}/ingest/${jobId}`, { method: 'DELETE' }).catch(() => {});
}

async function viteRunning() {
  try {
    return (await fetch('http://localhost:5173')).ok;
  } catch {
    return false;
  }
}

export async function launchApp() {
  const health = await fetch(`${API}/health`).catch(() => null);
  if (!health?.ok) throw new Error(`API not healthy at ${API}`);
  let vite;
  if (!(await viteRunning())) {
    vite = await createServer({ root: APP_DIR, server: { port: 5173, strictPort: true }, logLevel: 'error' });
    await vite.listen();
  }
  const env = { ...process.env, JAS_SKIP_ONBOARDING: '1' };
  delete env.ELECTRON_RUN_AS_NODE;
  const app = await electron.launch({ args: ['.'], cwd: APP_DIR, env });
  const page = await app.firstWindow();
  await page.waitForSelector('[data-testid="status-bar"]');
  return {
    app,
    page,
    close: async () => {
      await app.close();
      if (vite) await vite.close();
    },
  };
}

export async function screenshot(page, name) {
  mkdirSync(ARTIFACTS, { recursive: true });
  await page.screenshot({ path: path.join(ARTIFACTS, name) });
}
