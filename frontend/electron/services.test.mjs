import assert from 'node:assert/strict';
import childProcess from 'node:child_process';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { afterEach, mock, test } from 'node:test';

const { createServiceManager } = createRequire(import.meta.url)('./services.js');

const json = (body) => new Response(JSON.stringify(body), { status: 200 });
const lines = (...objs) => new Response(objs.map((o) => JSON.stringify(o)).join('\n') + '\n', { status: 200 });

function fakeFetch(routes) {
  mock.method(globalThis, 'fetch', async (url) => {
    const route = Object.keys(routes).find((r) => String(url).endsWith(r));
    if (!route) throw new Error(`connection refused: ${url}`);
    return routes[route]();
  });
}

function manager() {
  const updates = [];
  const m = createServiceManager((s) => updates.push(s));
  return { m, updates };
}

afterEach(() => mock.restoreAll());

test('leaves an already-running backend and Ollama alone', async () => {
  fakeFetch({
    '/health': () => json({ status: 'ok' }),
    '/status/services': () => json({ ollama: true, ollama_model_ready: true, ollama_model: 'llama3:8b' }),
  });
  const exists = mock.method(fs, 'existsSync', () => true);
  const { m } = manager();
  await m.start();
  assert.deepEqual([m.get().backend, m.get().answers], ['ready', 'ready']);
  assert.equal(exists.mock.callCount(), 0, 'looked for Docker even though the backend was up');
  await m.stop();
});

test('asks for Docker Desktop when the backend is down and Docker is not installed', async () => {
  fakeFetch({});
  mock.method(fs, 'existsSync', () => false);
  const { m } = manager();
  await m.start();
  assert.deepEqual([m.get().backend, m.get().answers], ['needs-docker', 'waiting']);
});

test('never opens Docker Desktop; reports it as stopped instead', async () => {
  fakeFetch({});
  mock.method(fs, 'existsSync', () => true);
  const calls = [];
  mock.method(childProcess, 'execFile', (file, args, _opts, cb) => {
    calls.push([file, ...args].join(' '));
    cb(new Error('Cannot connect to the Docker daemon'), '', '');
  });
  const { m } = manager();
  await m.start();
  assert.equal(m.get().backend, 'docker-stopped');
  assert.ok(calls.some((c) => c.endsWith('docker info')), 'did not check whether Docker is running');
  assert.ok(!calls.some((c) => /\bopen\b|compose/.test(c)), `tried to launch something: ${calls.join('; ')}`);
});

test('reports a missing model, then downloads it with progress', async () => {
  let modelReady = false;
  fakeFetch({
    '/health': () => json({ status: 'ok' }),
    '/status/services': () => json({ ollama: true, ollama_model_ready: modelReady, ollama_model: 'tiny:1b' }),
    '/api/pull': () => {
      modelReady = true;
      return lines({ status: 'pulling' }, { total: 200, completed: 50 }, { total: 200, completed: 200 }, { status: 'success' });
    },
  });
  const { m, updates } = manager();
  await m.start();
  assert.equal(m.get().answers, 'needs-model');
  assert.equal(m.get().model, 'tiny:1b');

  await m.pullModel();
  const progress = updates.filter((u) => u.answers === 'downloading').map((u) => u.progress);
  assert.deepEqual(progress, [0, 25, 100]);
  assert.equal(m.get().answers, 'ready');
});

test('a failed model download is reported, not swallowed', async () => {
  fakeFetch({
    '/health': () => json({ status: 'ok' }),
    '/status/services': () => json({ ollama: true, ollama_model_ready: false, ollama_model: 'tiny:1b' }),
    '/api/pull': () => lines({ total: 100, completed: 10 }, { error: 'disk full' }),
  });
  const { m } = manager();
  await m.start();
  await m.pullModel();
  assert.equal(m.get().answers, 'failed');
  assert.match(m.get().detail, /disk full/);
});

test('start() while already starting reuses the same run', async () => {
  fakeFetch({
    '/health': () => json({ status: 'ok' }),
    '/status/services': () => json({ ollama: true, ollama_model_ready: true }),
  });
  const { m } = manager();
  assert.equal(m.start(), m.start());
  await m.start();
});
