// UI acceptance test for US-F-15: one window gives a unified view of search,
// results and the knowledge graph across everything ingested.
//
//   cd frontend && node e2e/unified-view.e2e.mjs
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { WORK_DIR, forget, ingest, launchApp, screenshot } from './helpers.mjs';

const run = randomUUID().slice(0, 8);
const folder = path.join(WORK_DIR, `unified-${run}`);
const fileName = `lighthouse_note_${run}.txt`;
const QUESTION = 'Where did Odessa Varga say the lighthouse tour starts?';
let jobId;
let session;

const visible = (page, testId) => page.locator(`[data-testid="${testId}"]`).isVisible();

try {
  mkdirSync(folder, { recursive: true });
  const filePath = path.join(folder, fileName);
  writeFileSync(filePath, `Odessa Varga said the Point Pinos lighthouse tour starts at the north gate at 9 AM. Ref ${run}.\n`);
  jobId = await ingest(filePath, 'txt');

  session = await launchApp();
  const { app, page } = session;
  const oneWindow = () => assert.equal(app.windows().length, 1, 'the app opened a second window');

  for (const label of ['Search', 'Knowledge Graph', 'Settings']) {
    const item = page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: label, exact: true });
    assert.ok(await item.isVisible(), `nav item ${label}`);
  }
  oneWindow();

  const search = page.locator('input').first();
  await search.fill(QUESTION);
  await search.press('Enter');
  await page.locator('[data-testid="result-file"]', { hasText: fileName }).waitFor({ timeout: 180_000 });
  const cardCount = await page.locator('[data-testid="result-card"]').count();
  assert.ok(await visible(page, 'status-bar'), 'status bar on the results screen');
  await screenshot(page, 'unified-search.png');

  await page.getByTestId('nav-graph').click();
  assert.ok(await visible(page, 'graph-screen'), 'knowledge graph screen shown');
  assert.ok(!(await visible(page, 'results-screen')), 'results hidden while on the graph');
  assert.ok(await visible(page, 'status-bar'), 'status bar on the graph screen');
  assert.equal(await page.getByTestId('nav-graph').getAttribute('aria-current'), 'page');
  oneWindow();
  await screenshot(page, 'unified-graph.png');

  await page.getByTestId('nav-settings').click();
  await page.locator('[data-testid="indexed-file"]', { hasText: fileName }).waitFor({ timeout: 10_000 });
  assert.ok(await visible(page, 'status-bar'), 'status bar on the settings screen');
  oneWindow();
  await screenshot(page, 'unified-settings.png');

  await page.getByTestId('nav-search').click();
  assert.ok(await visible(page, 'results-screen'), 'results screen back');
  assert.equal(await search.inputValue(), QUESTION, 'query kept');
  assert.ok(!(await page.getByText('Searching...').isVisible()), 'results were not fetched again');
  assert.equal(await page.locator('[data-testid="result-card"]').count(), cardCount, 'same results kept');
  assert.ok(await page.locator('[data-testid="result-file"]', { hasText: fileName }).isVisible());
  oneWindow();

  console.log(`PASS US-F-15: search, results, knowledge graph and settings in one window; ${cardCount} results kept across views`);
} catch (err) {
  console.error(`FAIL US-F-15: ${err.message}`);
  process.exitCode = 1;
} finally {
  if (session) await session.close();
  await forget(jobId);
  rmSync(folder, { recursive: true, force: true });
}
