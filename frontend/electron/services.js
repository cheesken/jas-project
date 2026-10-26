const childProcess = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const API = 'http://localhost:8000';
const OLLAMA = 'http://localhost:11434';
const COMPOSE_FILE = path.resolve(__dirname, '..', '..', 'docker-compose.yml');
const DOCKER_APP = '/Applications/Docker.app';
const BIN_DIRS = [
  '/usr/local/bin',
  '/opt/homebrew/bin',
  path.join(os.homedir(), '.docker', 'bin'),
  path.join(DOCKER_APP, 'Contents', 'Resources', 'bin'),
  '/Applications/Ollama.app/Contents/Resources',
];
const ENV = { ...process.env, PATH: [...BIN_DIRS, process.env.PATH || ''].join(':') };

const BACKEND_START_TIMEOUT_MS = 45 * 60 * 1000;
const OLLAMA_START_TIMEOUT_MS = 30 * 1000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function findBinary(name) {
  return BIN_DIRS.map((d) => path.join(d, name)).find((p) => fs.existsSync(p)) || null;
}

function run(file, args) {
  return new Promise((resolve) => {
    childProcess.execFile(file, args, { env: ENV, maxBuffer: 16 * 1024 * 1024 }, (error, stdout, stderr) => {
      resolve({ ok: !error, output: `${stdout}${stderr}`.trim() });
    });
  });
}

async function getJSON(url, timeoutMs = 3000) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

async function waitFor(check, timeoutMs, intervalMs = 2000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await check()) return true;
    await sleep(intervalMs);
  }
  return false;
}

function createServiceManager(onUpdate) {
  const state = { backend: 'checking', answers: 'checking', model: 'llama3:8b', progress: null, detail: '' };
  let startedBackend = false;
  let ollamaChild = null;
  let running = null;

  const set = (patch) => {
    Object.assign(state, patch);
    onUpdate({ ...state });
  };

  const backendUp = async () => Boolean(await getJSON(`${API}/health`));

  async function ensureBackend() {
    if (await backendUp()) return set({ backend: 'ready' });
    const docker = findBinary('docker');
    if (!docker || !fs.existsSync(DOCKER_APP)) return set({ backend: 'needs-docker' });

    if (!(await run(docker, ['info'])).ok) return set({ backend: 'docker-stopped' });
    set({ backend: 'starting' });

    if (!(await run(docker, ['image', 'inspect', 'jas-project-api'])).ok) set({ backend: 'first-run' });
    const up = await run(docker, ['compose', '-f', COMPOSE_FILE, 'up', '-d']);
    if (!up.ok) return set({ backend: 'failed', detail: up.output.split('\n').slice(-3).join('\n') });
    startedBackend = true;

    if (!(await waitFor(backendUp, BACKEND_START_TIMEOUT_MS))) {
      return set({ backend: 'failed', detail: 'The search service started but did not respond.' });
    }
    set({ backend: 'ready' });
  }

  async function answersState() {
    const s = await getJSON(`${API}/status/services`, 8000);
    if (s?.ollama_model) state.model = s.ollama_model;
    if (!s?.ollama) return 'down';
    return s.ollama_model_ready ? 'ready' : 'needs-model';
  }

  async function ensureAnswers() {
    let answers = await answersState();
    if (answers === 'down') {
      const ollama = findBinary('ollama');
      if (!ollama) return set({ answers: 'needs-ollama' });
      set({ answers: 'starting' });
      ollamaChild = childProcess.spawn(ollama, ['serve'], { env: ENV, stdio: 'ignore' });
      ollamaChild.on('exit', () => {
        ollamaChild = null;
      });
      await waitFor(async () => Boolean(await getJSON(`${OLLAMA}/api/tags`)), OLLAMA_START_TIMEOUT_MS, 1000);
      answers = await answersState();
      if (answers === 'down') return set({ answers: 'failed', detail: 'Ollama did not start.' });
    }
    set({ answers });
  }

  function start() {
    if (!running) {
      running = (async () => {
        set({ backend: 'checking', answers: 'checking', detail: '', progress: null });
        await ensureBackend();
        if (state.backend === 'ready') await ensureAnswers();
        else set({ answers: 'waiting' });
      })().finally(() => {
        running = null;
      });
    }
    return running;
  }

  async function pullModel() {
    if (state.answers === 'downloading') return;
    set({ answers: 'downloading', progress: 0 });
    try {
      const res = await fetch(`${OLLAMA}/api/pull`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: state.model, stream: true }),
      });
      if (!res.ok) throw new Error(`Ollama returned ${res.status}`);
      const decoder = new TextDecoder();
      let buffer = '';
      for await (const chunk of res.body) {
        buffer += decoder.decode(chunk, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          const msg = JSON.parse(line);
          if (msg.error) throw new Error(msg.error);
          if (msg.total && msg.completed) set({ progress: Math.floor((100 * msg.completed) / msg.total) });
        }
      }
      set({ answers: (await answersState()) === 'ready' ? 'ready' : 'failed', progress: null });
    } catch (err) {
      set({ answers: 'failed', progress: null, detail: `The model download stopped: ${err.message}` });
    }
  }

  async function stop() {
    if (ollamaChild) ollamaChild.kill();
    if (startedBackend) {
      const docker = findBinary('docker');
      if (docker) await run(docker, ['compose', '-f', COMPOSE_FILE, 'stop']);
    }
  }

  return { start, pullModel, stop, get: () => ({ ...state }) };
}

module.exports = { createServiceManager };
