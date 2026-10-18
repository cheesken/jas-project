import React, { useCallback, useEffect, useState } from 'react';
import { api, pickFolder } from '../api';
import { uploadFile, importChromeHistory } from '../ingest';
import { COLORS, buttons } from '../ui';

const STEPS = ['welcome', 'check', 'data', 'done'];

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
  checks: { display: 'flex', flexDirection: 'column', gap: '8px' },
  check: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
    padding: '10px 14px',
    backgroundColor: COLORS.card,
    border: `1px solid ${COLORS.border}`,
    borderRadius: '8px',
    fontSize: '14px',
  },
  mark: { fontWeight: 700, width: '16px', flexShrink: 0 },
  fix: { display: 'block', fontSize: '13px', color: COLORS.muted, marginTop: '2px' },
  code: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: '12px' },
  actions: { display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' },
  dataButtons: { display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'flex-start' },
  folder: { fontSize: '13px', color: COLORS.text, overflowWrap: 'anywhere' },
};

function Check({ ok, label, fix, testId }) {
  return (
    <div style={styles.check} data-testid={testId} data-ok={ok ? 'true' : 'false'}>
      <span style={{ ...styles.mark, color: ok ? COLORS.good : COLORS.bad }} aria-hidden="true">{ok ? '✓' : '✕'}</span>
      <span>
        {label}
        {!ok && fix && <span style={styles.fix}>{fix}</span>}
      </span>
    </div>
  );
}

export default function OnboardingScreen({ onFinish, showToast }) {
  const [step, setStep] = useState(0);
  const [services, setServices] = useState(null);
  const [checking, setChecking] = useState(false);
  const [folders, setFolders] = useState([]);

  const runChecks = useCallback(async () => {
    setChecking(true);
    try {
      setServices(await api('/status/services'));
    } catch {
      setServices({ api: false, vector_store: false, ollama: false, ollama_model: 'llama3:8b', ollama_model_ready: false });
    }
    setChecking(false);
  }, []);

  useEffect(() => {
    if (STEPS[step] === 'check') runChecks();
  }, [step, runChecks]);

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));

  const addFolder = async () => {
    const path = await pickFolder();
    if (!path) return;
    try {
      const { path: saved } = await api('/settings/watch', { method: 'POST', body: JSON.stringify({ path }) });
      setFolders((prev) => (prev.includes(saved) ? prev : [...prev, saved]));
      showToast(`Watching ${saved.split('/').pop()}. Files already in it are being indexed.`, 'success');
    } catch (err) {
      showToast(`Could not watch that folder: ${err.message}`, 'error');
    }
  };

  const allReady = services && services.api && services.vector_store && services.ollama && services.ollama_model_ready;
  const skip = <button style={buttons.link} onClick={onFinish} data-testid="onboarding-skip">Skip setup</button>;

  return (
    <div style={styles.page} data-testid="onboarding">
      <div style={styles.panel}>
        <span style={styles.step}>Step {step + 1} of {STEPS.length}</span>

        {STEPS[step] === 'welcome' && (
          <>
            <h1 style={styles.title}>Your memory, on your Mac.</h1>
            <p style={styles.text}>
              Search your documents, screenshots and browsing history by asking questions in plain language.
              Everything is indexed and answered on this computer. Nothing is sent to the internet.
            </p>
            <div style={styles.actions}>
              <button style={buttons.primary} onClick={next}>Get started</button>
              {skip}
            </div>
          </>
        )}

        {STEPS[step] === 'check' && (
          <>
            <h1 style={styles.title}>Checking your setup</h1>
            {!services ? (
              <p style={styles.text}>Checking...</p>
            ) : (
              <div style={styles.checks}>
                <Check testId="check-api" ok={services.api} label="Backend"
                  fix={<>Start it with <code style={styles.code}>docker compose up -d</code></>} />
                <Check testId="check-index" ok={services.vector_store} label="Search index"
                  fix={<>Restart the backend with <code style={styles.code}>docker compose up -d</code></>} />
                <Check testId="check-ollama" ok={services.ollama} label="Ollama (for written answers)"
                  fix={<>Start it with <code style={styles.code}>ollama serve</code></>} />
                <Check testId="check-model" ok={services.ollama_model_ready} label={`Language model ${services.ollama_model}`}
                  fix={<>Download it with <code style={styles.code}>ollama pull {services.ollama_model}</code></>} />
              </div>
            )}
            {services && !allReady && (
              <p style={styles.text}>Search still works without Ollama. You just won't get written answers.</p>
            )}
            <div style={styles.actions}>
              <button style={buttons.primary} onClick={next} disabled={!services?.api}>
                {allReady ? 'Continue' : 'Continue anyway'}
              </button>
              <button style={buttons.secondary} onClick={runChecks} disabled={checking}>
                {checking ? 'Checking...' : 'Check again'}
              </button>
              {skip}
            </div>
          </>
        )}

        {STEPS[step] === 'data' && (
          <>
            <h1 style={styles.title}>Add your data</h1>
            <p style={styles.text}>
              Watch a folder to index what's in it now and anything you add later, or add files one at a time.
              You can change this later in Settings.
            </p>
            <div style={styles.dataButtons}>
              <button style={buttons.primary} onClick={addFolder}>Watch a folder</button>
              {folders.map((f) => <span key={f} style={styles.folder} data-testid="onboarding-folder">Watching {f}</span>)}
              <button style={buttons.secondary} onClick={() => uploadFile(showToast)}>Upload a file</button>
              <button style={buttons.secondary} onClick={() => importChromeHistory(showToast)}>Import Chrome history</button>
            </div>
            <div style={styles.actions}>
              <button style={buttons.primary} onClick={next}>Continue</button>
              {skip}
            </div>
          </>
        )}

        {STEPS[step] === 'done' && (
          <>
            <h1 style={styles.title}>You're all set</h1>
            <p style={styles.text}>
              Indexing runs in the background, and the bar at the bottom of the window shows its progress.
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
