// UI acceptance test for US-F-16: the status panel shows what share of the
// user's documents is indexed and when the index was last updated, and keeps
// up as files are added or fail.
//
//   cd frontend && node e2e/status-panel.e2e.mjs
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { WORK_DIR, forget, getJSON, ingest, launchApp, screenshot, sleep } from './helpers.mjs';

const POLL_BUDGET_MS = 15_000;
const run = randomUUID().slice(0, 8);
const folder = path.join(WORK_DIR, `status-${run}`);
const jobs = [];
let session;

async function readBar(page) {
  const text = async (id) => (await page.getByTestId(id).textContent()).trim();
  const num = (s) => Number((s.match(/\d+/) || ['NaN'])[0]);
  const percent = await text('status-percent');
  return {
    docs: num(await text('status-docs')),
    percent: /Nothing added yet/.test(percent) ? null : num(percent),
    updated: await text('status-updated'),
    pending: num(await text('status-pending')),
    errors: num(await text('status-failed')),
  };
}

async function waitForBar(page, predicate, what) {
  const deadline = Date.now() + POLL_BUDGET_MS;
  let bar;
  while (Date.now() < deadline) {
    bar = await readBar(page);
    if (predicate(bar)) return bar;
    await sleep(500);
  }
  throw new Error(`status bar never showed ${what}; last read ${JSON.stringify(bar)}`);
}

const matchesApi = (bar, api) =>
  bar.docs === api.total_docs && bar.percent === api.percent_indexed &&
  bar.errors === api.failed_docs && bar.pending === api.pending_jobs;

try {
  mkdirSync(folder, { recursive: true });
  session = await launchApp();
  const { page } = session;
  await page.getByTestId('status-docs').waitFor();

  const before = await getJSON('/status');
  await waitForBar(page, (b) => matchesApi(b, before), 'the same numbers as GET /status');

  const note = path.join(folder, `status_note_${run}.txt`);
  writeFileSync(note, `Marisol Okafor renewed the Willow Creek library card on October 14. Ref ${run}.\n`);
  jobs.push(await ingest(note, 'txt'));
  const afterNote = await getJSON('/status');
  assert.equal(afterNote.total_docs, before.total_docs + 1);
  const bar = await waitForBar(page, (b) => b.docs === afterNote.total_docs, 'the new document count');
  assert.equal(bar.updated, 'Last updated just now');
  assert.equal(bar.percent, afterNote.percent_indexed);
  await screenshot(page, 'status-after-upload.png');

  const broken = path.join(folder, `broken_scan_${run}.png`);
  writeFileSync(broken, 'not really a png');
  jobs.push(await ingest(broken, 'image', { expect: 'FAILED' }));
  const afterFail = await getJSON('/status');
  assert.equal(afterFail.failed_docs, before.failed_docs + 1);
  assert.ok(afterFail.percent_indexed < 100, `percent should drop below 100, got ${afterFail.percent_indexed}`);
  await waitForBar(page, (b) => matchesApi(b, afterFail), 'the failed file and lower percentage');
  await screenshot(page, 'status-after-failure.png');

  while (jobs.length) await forget(jobs.pop());
  const restored = await getJSON('/status');
  assert.equal(restored.total_docs, before.total_docs);
  await waitForBar(page, (b) => matchesApi(b, restored), 'the original numbers after cleanup');

  console.log(`PASS US-F-16: status bar tracked ${before.total_docs} -> ${afterNote.total_docs} documents, ` +
    `showed "just now", and ${afterFail.percent_indexed}% with 1 more error after a failed file`);
} catch (err) {
  console.error(`FAIL US-F-16: ${err.message}`);
  process.exitCode = 1;
} finally {
  if (session) await session.close();
  for (const id of jobs) await forget(id);
  rmSync(folder, { recursive: true, force: true });
}
