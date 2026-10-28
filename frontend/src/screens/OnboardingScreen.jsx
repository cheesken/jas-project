import React, { useEffect, useState } from 'react';
import { api, pickFolder } from '../api';
import { uploadFile, importChromeHistory, importSafariHistory, safariAvailable } from '../ingest';
import { COLORS, buttons } from '../ui';
import { STARTING, canManageServices, useServices } from '../useServices';

const STEPS = ['welcome', 'data', 'done'];

const styles = {
  page: {
    height: '100%',
    overflowY: 'auto',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '48px 16px',
    boxSizing: 'border-box',
  },
  panel: { width: '100%', maxWidth: '520px', display: 'flex', flexDirection: 'column', gap: '18px' },
  step: { fontSize: '12px', letterSpacing: '0.06em', textTransform: 'uppercase', color: COLORS.muted, fontWeight: 600 },
  title: { fontSize: '28px', fontWeight: 600, margin: 0, color: COLORS.text, textWrap: 'balance' },
  text: { fontSize: '15px', color: COLORS.muted, margin: 0, lineHeight: 1.55 },
  notice: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    padding: '16px',
    backgroundColor: COLORS.card,
    border: `1px solid ${COLORS.border}`,
    borderRadius: '8px',
  },
  noticeTitle: { fontSize: '16px', fontWeight: 600, margin: 0, color: COLORS.text },
  summary: { cursor: 'pointer', fontSize: '14px', color: COLORS.accent, fontWeight: 600 },
  detail: { margin: '8px 0 0', fontSize: '13px', color: COLORS.text, lineHeight: 1.6, whiteSpace: 'pre-wrap' },
  code: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
    fontSize: '13px',
    backgroundColor: COLORS.page,
    padding: '1px 6px',
    borderRadius: '4px',
  },
  track: { height: '8px', borderRadius: '4px', backgroundColor: COLORS.sidebar, overflow: 'hidden' },
  fill: { height: '100%', backgroundColor: COLORS.accent, transition: 'width 0.3s ease' },
  actions: { display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' },
  dataButtons: { display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'flex-start' },
  folder: { fontSize: '13px', color: COLORS.text, overflowWrap: 'anywhere' },
};

async function browserReadiness() {
  try {
    const s = await api('/status/services');
    const answers = !s.ollama ? 'needs-ollama' : s.ollama_model_ready ? 'ready' : 'needs-model';
    return { backend: s.api && s.vector_store ? 'ready' : 'unavailable', answers, model: s.ollama_model };
  } catch {
    return { backend: 'unavailable', answers: 'waiting', model: 'llama3:8b' };
  }
}

function Notice({ title, children, testId }) {
  return (
    <div style={styles.notice} data-testid={testId}>
      <h2 style={styles.noticeTitle}>{title}</h2>
      {children}
    </div>
  );
}

function Details({ children }) {
  return (
    <details>
      <summary style={styles.summary}>Details</summary>
      <p style={styles.detail}>{children}</p>
    </details>
  );
}

export default function OnboardingScreen({ onFinish, showToast }) {
  const managed = canManageServices();
  const live = useServices();
  const [browserState, setBrowserState] = useState(null);
  const [phase, setPhase] = useState('welcome');
  const [folders, setFolders] = useState([]);
  const state = managed ? live : browserState;
  const ready = state?.backend === 'ready' && state?.answers === 'ready';

  useEffect(() => {
    if (phase === 'setup' && ready) setPhase('data');
  }, [phase, ready]);

  const retry = async () => {
    if (managed) {
      window.electronAPI.startServices();
    } else {
      setBrowserState(null);
      setBrowserState(await browserReadiness());
    }
  };

  const getStarted = () => {
    setPhase('setup');
    if (!managed) retry();
  };

  const addFolder = async () => {
    const path = await pickFolder();
    if (!path) return;
    try {
      const { path: saved } = await api('/settings/watch', { method: 'POST', body: JSON.stringify({ path }) });
      setFolders((prev) => (prev.includes(saved) ? prev : [...prev, saved]));
      showToast(`Watching ${saved.split('/').pop()}. Files already in it are being added.`, 'success');
    } catch (err) {
      showToast(`Could not watch that folder: ${err.message}`, 'error');
    }
  };

  const skip = <button style={buttons.link} onClick={onFinish} data-testid="onboarding-skip">Skip setup</button>;
  const continueWithout = (
    <button style={buttons.secondary} onClick={() => setPhase('data')}>Continue without answers</button>
  );

  const setupView = () => {
    if (!state || STARTING.includes(state.backend)) {
      const firstRun = state?.backend === 'first-run';
      return (
        <>
          <h1 style={styles.title}>{firstRun ? 'Setting up for the first time' : 'Getting Personal Memory ready'}</h1>
          <p style={styles.text} data-testid="setup-starting">
            {firstRun
              ? 'Personal Memory is preparing its search engine. This happens once, can take 20 minutes or more, and needs an internet connection until it finishes.'
              : 'This usually takes less than a minute.'}
          </p>
          <div style={styles.actions}>{skip}</div>
        </>
      );
    }

    if (state.backend === 'needs-docker') {
      return (
        <>
          <h1 style={styles.title}>One more app to install</h1>
          <Notice title="Personal Memory needs Docker Desktop" testId="notice-docker">
            <p style={styles.text}>
              Docker Desktop is a free app that Personal Memory uses to run its search engine privately on this Mac.
              Install it, open it once, then come back here.
            </p>
          </Notice>
          <div style={styles.actions}>
            <button style={buttons.primary} onClick={() => window.electronAPI.openDownload('docker')}>Download Docker Desktop</button>
            <button style={buttons.secondary} onClick={retry}>I've installed it</button>
            {skip}
          </div>
        </>
      );
    }

    if (state.backend === 'docker-stopped') {
      return (
        <>
          <h1 style={styles.title}>Open Docker Desktop</h1>
          <Notice title="Docker Desktop isn't running" testId="notice-docker-stopped">
            <p style={styles.text}>
              Personal Memory runs its search engine in Docker Desktop. Open Docker Desktop from your Applications
              folder, wait until it says it's running, then come back here.
            </p>
          </Notice>
          <div style={styles.actions}>
            <button style={buttons.primary} onClick={retry}>Try again</button>
            {skip}
          </div>
        </>
      );
    }

    if (state.backend !== 'ready') {
      return (
        <>
          <h1 style={styles.title}>Search couldn't start</h1>
          <Notice title="Personal Memory can't add or find files right now" testId="notice-search">
            <p style={styles.text}>Make sure Docker Desktop is open, then try again.</p>
            {managed ? (
              state.detail && <Details>{state.detail}</Details>
            ) : (
              <Details>In Terminal, run <code style={styles.code}>docker compose up -d</code> in the project folder.</Details>
            )}
          </Notice>
          <div style={styles.actions}>
            <button style={buttons.primary} onClick={retry}>Try again</button>
            {skip}
          </div>
        </>
      );
    }

    if (state.answers === 'needs-ollama') {
      return (
        <>
          <h1 style={styles.title}>Turn on written answers</h1>
          <Notice title="Written answers need Ollama" testId="notice-ollama">
            <p style={styles.text}>
              Ollama is a free app that runs the AI privately on this Mac. Without it you can still search your
              files and see what matches; you just won't get a written answer.
            </p>
          </Notice>
          <div style={styles.actions}>
            {managed && <button style={buttons.primary} onClick={() => window.electronAPI.openDownload('ollama')}>Download Ollama</button>}
            <button style={buttons.secondary} onClick={retry}>{managed ? "I've installed it" : 'Try again'}</button>
            {continueWithout}
          </div>
        </>
      );
    }

    if (state.answers === 'needs-model' || state.answers === 'downloading') {
      const downloading = state.answers === 'downloading';
      return (
        <>
          <h1 style={styles.title}>{downloading ? 'Downloading the AI model' : 'Download the AI model'}</h1>
          <Notice title={`Written answers use ${state.model}`} testId="notice-model">
            <p style={styles.text}>
              It's a one-time download of a few gigabytes. After that it runs entirely on this Mac.
              {downloading && ' You can keep going while it downloads.'}
            </p>
            {downloading && (
              <div style={styles.track} role="progressbar" aria-valuenow={state.progress || 0} aria-valuemin={0} aria-valuemax={100}>
                <div style={{ ...styles.fill, width: `${state.progress || 0}%` }} />
              </div>
            )}
          </Notice>
          <div style={styles.actions}>
            {managed && !downloading && (
              <button style={buttons.primary} onClick={() => window.electronAPI.pullModel()}>Download model</button>
            )}
            {!managed && <Details>In Terminal, run <code style={styles.code}>ollama pull {state.model}</code></Details>}
            {downloading ? <button style={buttons.primary} onClick={() => setPhase('data')}>Keep going</button> : continueWithout}
          </div>
        </>
      );
    }

    if (STARTING.includes(state.answers)) {
      return (
        <>
          <h1 style={styles.title}>Getting Personal Memory ready</h1>
          <p style={styles.text} data-testid="setup-starting">Starting the AI for written answers.</p>
          <div style={styles.actions}>{continueWithout}</div>
        </>
      );
    }

    return (
      <>
        <h1 style={styles.title}>Written answers couldn't start</h1>
        <Notice title="You can still search your files" testId="notice-answers">
          <p style={styles.text}>Personal Memory couldn't start the AI that writes answers.</p>
          {state.detail && <Details>{state.detail}</Details>}
        </Notice>
        <div style={styles.actions}>
          <button style={buttons.primary} onClick={retry}>Try again</button>
          {continueWithout}
        </div>
      </>
    );
  };

  const stepIndex = STEPS.indexOf(phase);

  return (
    <div style={styles.page} data-testid="onboarding">
      <div style={styles.panel}>
        {stepIndex >= 0 && <span style={styles.step}>Step {stepIndex + 1} of {STEPS.length}</span>}

        {phase === 'welcome' && (
          <>
            <h1 style={styles.title}>Your memory, on your Mac.</h1>
            <p style={styles.text}>
              Search your documents, screenshots and browsing history by asking questions in plain language.
              Everything is indexed and answered on this computer. Nothing is sent to the internet.
            </p>
            <div style={styles.actions}>
              <button style={buttons.primary} onClick={getStarted}>Get started</button>
              {skip}
            </div>
          </>
        )}

        {phase === 'setup' && setupView()}

        {phase === 'data' && (
          <>
            <h1 style={styles.title}>Add your files</h1>
            <p style={styles.text}>
              Pick a folder to add everything in it now and anything you save there later, or add files one at a time.
              You can change this later in Settings.
            </p>
            <div style={styles.dataButtons}>
              <button style={buttons.primary} onClick={addFolder}>Choose a folder</button>
              {folders.map((f) => <span key={f} style={styles.folder} data-testid="onboarding-folder">Adding files from {f}</span>)}
              <button style={buttons.secondary} onClick={() => uploadFile(showToast)}>Add a file</button>
              <button style={buttons.secondary} onClick={() => importChromeHistory(showToast)}>Add Chrome history</button>
              {safariAvailable() && (
                <button style={buttons.secondary} onClick={() => importSafariHistory(showToast)}>Add Safari history</button>
              )}
            </div>
            <div style={styles.actions}>
              <button style={buttons.primary} onClick={() => setPhase('done')}>Continue</button>
              {skip}
            </div>
          </>
        )}

        {phase === 'done' && (
          <>
            <h1 style={styles.title}>You're all set</h1>
            <p style={styles.text}>
              Your files are being added in the background, and the bar at the bottom of the window shows how far along it is.
              Try asking about something in your files, like when a bill is due or where you parked.
            </p>
            <div style={styles.actions}>
              <button style={buttons.primary} onClick={onFinish} data-testid="onboarding-finish">Start searching</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
