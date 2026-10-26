import React, { useCallback, useEffect, useState } from 'react';
import { api, pickFolder, timeAgo } from '../api';
import { COLORS, FONT, buttons } from '../ui';

const TYPE_LABELS = { pdf: 'PDF', txt: 'Text', image: 'Image', browser_history: 'Browser history' };

const styles = {
  main: { flex: 1, overflowY: 'auto', padding: '40px', boxSizing: 'border-box' },
  page: { maxWidth: '760px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '28px' },
  title: { fontSize: '24px', fontWeight: 600, margin: 0, color: COLORS.text },
  section: { display: 'flex', flexDirection: 'column', gap: '10px' },
  heading: { fontSize: '16px', fontWeight: 600, margin: 0, color: COLORS.text },
  hint: { fontSize: '13px', color: COLORS.muted, margin: 0 },
  row: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '12px',
    padding: '10px 14px',
    backgroundColor: COLORS.card,
    border: `1px solid ${COLORS.border}`,
    borderRadius: '8px',
    fontSize: '14px',
  },
  path: { minWidth: 0, overflowWrap: 'anywhere', color: COLORS.text },
  stats: {
    display: 'grid',
    gridTemplateColumns: '1fr auto',
    gap: '6px 16px',
    padding: '14px',
    backgroundColor: COLORS.card,
    border: `1px solid ${COLORS.border}`,
    borderRadius: '8px',
    fontSize: '14px',
    fontVariantNumeric: 'tabular-nums',
  },
  statLabel: { color: COLORS.muted },
  statValue: { textAlign: 'right', color: COLORS.text },
  tableWrap: { overflowX: 'auto', backgroundColor: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: '8px' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '13px', fontFamily: FONT },
  th: { textAlign: 'left', padding: '8px 12px', color: COLORS.muted, fontWeight: 600, borderBottom: `1px solid ${COLORS.border}` },
  td: { padding: '8px 12px', borderBottom: `1px solid ${COLORS.sidebar}`, color: COLORS.text },
  danger: {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '12px',
    padding: '14px',
    backgroundColor: COLORS.dangerSoft,
    border: `1px solid ${COLORS.bad}`,
    borderRadius: '8px',
    fontSize: '14px',
  },
  actions: { display: 'flex', gap: '8px', flexWrap: 'wrap' },
};

export default function SettingsScreen({ showToast, onRestartSetup }) {
  const [dirs, setDirs] = useState([]);
  const [status, setStatus] = useState(null);
  const [files, setFiles] = useState([]);
  const [error, setError] = useState(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const load = useCallback(async () => {
    try {
      const [w, s, f] = await Promise.all([api('/settings/watch'), api('/status'), api('/ingest')]);
      setDirs(w.paths);
      setStatus(s);
      setFiles(f.files);
      setError(null);
    } catch {
      setError("Search isn't running, so settings can't be loaded. Start it with docker compose up -d");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const addFolder = async () => {
    const path = await pickFolder();
    if (!path) return;
    try {
      await api('/settings/watch', { method: 'POST', body: JSON.stringify({ path }) });
      showToast(`Watching ${path.split('/').pop()}. Files already in it are being indexed.`, 'success');
      load();
    } catch (err) {
      showToast(`Could not watch that folder: ${err.message}`, 'error');
    }
  };

  const removeFolder = async (path) => {
    try {
      await api(`/settings/watch/${encodeURIComponent(path)}`, { method: 'DELETE' });
      showToast(`Stopped watching ${path.split('/').pop()}. Its files stay searchable.`, 'info');
      load();
    } catch (err) {
      showToast(`Could not remove that folder: ${err.message}`, 'error');
    }
  };

  const removeFile = async (file) => {
    try {
      await api(`/ingest/${file.job_id}`, { method: 'DELETE' });
      showToast(`Removed ${file.file_name} from the index.`, 'info');
      load();
    } catch (err) {
      showToast(`Could not remove ${file.file_name}: ${err.message}`, 'error');
    }
  };

  const clearIndex = async () => {
    try {
      const { files_removed: n } = await api('/ingest', { method: 'DELETE' });
      showToast(`Cleared the index (${n} file${n === 1 ? '' : 's'} removed).`, 'success');
      setConfirmClear(false);
      load();
    } catch (err) {
      showToast(`Could not clear the index: ${err.message}`, 'error');
    }
  };

  const byType = status?.by_type || {};
  const stat = (label, value, testId) => (
    <React.Fragment key={label}>
      <span style={styles.statLabel}>{label}</span>
      <span style={styles.statValue} data-testid={testId}>{value}</span>
    </React.Fragment>
  );

  return (
    <div style={styles.main} data-testid="settings-screen">
      <div style={styles.page}>
        <h1 style={styles.title}>Settings</h1>
        {error && <p style={{ ...styles.hint, color: COLORS.bad }}>{error}</p>}

        <section style={styles.section} aria-labelledby="watched-heading">
          <h2 id="watched-heading" style={styles.heading}>Watched folders</h2>
          <p style={styles.hint}>New and changed files in these folders are indexed automatically.</p>
          {dirs.length === 0 && <p style={styles.hint}>No folders are being watched yet.</p>}
          {dirs.map((path) => (
            <div key={path} style={styles.row} data-testid="watched-folder">
              <span style={styles.path}>{path}</span>
              <button style={buttons.small} onClick={() => removeFolder(path)}>Remove</button>
            </div>
          ))}
          <div><button style={buttons.primary} onClick={addFolder}>Add folder</button></div>
        </section>

        <section style={styles.section} aria-labelledby="status-heading">
          <h2 id="status-heading" style={styles.heading}>Index status</h2>
          {status && (
            <div style={styles.stats}>
              {stat('Total documents indexed', status.total_docs, 'settings-total')}
              {stat('Documents (PDF and text)', (byType.pdf || 0) + (byType.txt || 0))}
              {stat('Browser history', byType.browser_history || 0)}
              {stat('Images', byType.image || 0)}
              {stat('Indexed', status.percent_indexed === null ? 'Nothing added yet' : `${status.percent_indexed}%`)}
              {stat('Last successful ingestion', timeAgo(status.last_updated))}
              {stat('In progress', status.pending_jobs)}
              {stat('Failed', status.failed_docs)}
            </div>
          )}
        </section>

        <section style={styles.section} aria-labelledby="files-heading">
          <h2 id="files-heading" style={styles.heading}>Indexed files</h2>
          {files.length === 0 ? (
            <p style={styles.hint}>Nothing has been added yet.</p>
          ) : (
            <div style={styles.tableWrap}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>File</th>
                    <th style={styles.th}>Type</th>
                    <th style={styles.th}>Status</th>
                    <th style={styles.th}>Indexed</th>
                    <th style={styles.th}><span hidden>Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((f) => (
                    <tr key={f.job_id} data-testid="indexed-file">
                      <td style={{ ...styles.td, overflowWrap: 'anywhere' }}>{f.file_name}</td>
                      <td style={styles.td}>{TYPE_LABELS[f.file_type] || f.file_type}</td>
                      <td style={{ ...styles.td, color: f.status === 'FAILED' ? COLORS.bad : COLORS.text }} title={f.error_message || ''}>
                        {f.status.charAt(0) + f.status.slice(1).toLowerCase()}
                      </td>
                      <td style={styles.td}>{f.completed_at ? timeAgo(f.completed_at) : ''}</td>
                      <td style={{ ...styles.td, textAlign: 'right' }}>
                        <button style={buttons.small} onClick={() => removeFile(f)}>Remove</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section style={styles.section} aria-labelledby="setup-heading">
          <h2 id="setup-heading" style={styles.heading}>Setup</h2>
          <div><button style={buttons.secondary} onClick={onRestartSetup}>Run setup again</button></div>
        </section>

        <section style={styles.section} aria-labelledby="danger-heading">
          <h2 id="danger-heading" style={{ ...styles.heading, color: COLORS.bad }}>Danger zone</h2>
          <div style={styles.danger}>
            <span>
              {confirmClear
                ? 'This permanently deletes every embedding, all file records and the knowledge graph. Your files are not touched.'
                : 'Clear all indexed data.'}
            </span>
            <div style={styles.actions}>
              {confirmClear && <button style={buttons.secondary} onClick={() => setConfirmClear(false)}>Cancel</button>}
              <button style={buttons.danger} onClick={confirmClear ? clearIndex : () => setConfirmClear(true)}>
                {confirmClear ? 'Yes, clear everything' : 'Clear index'}
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
