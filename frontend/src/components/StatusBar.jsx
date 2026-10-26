import React, { useEffect, useState } from 'react';
import { api, timeAgo } from '../api';
import { COLORS, FONT } from '../ui';
import { STARTING, canManageServices, useServices } from '../useServices';

export const STATUS_POLL_MS = 5000;

const styles = {
  bar: {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: '6px 18px',
    padding: '10px 24px',
    borderTop: `1px solid ${COLORS.border}`,
    backgroundColor: COLORS.sidebar,
    fontSize: '12px',
    fontFamily: FONT,
    color: COLORS.muted,
    fontVariantNumeric: 'tabular-nums',
  },
  dot: { width: '8px', height: '8px', borderRadius: '50%', display: 'inline-block', marginRight: '6px' },
  item: { display: 'inline-flex', alignItems: 'center' },
};

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

export default function StatusBar() {
  const [status, setStatus] = useState(null);
  const [watched, setWatched] = useState(0);
  const [offline, setOffline] = useState(false);
  const [, setTick] = useState(0);
  const services = useServices();

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [s, w] = await Promise.all([api('/status'), api('/settings/watch')]);
        if (cancelled) return;
        setStatus(s);
        setWatched(w.paths.length);
        setOffline(false);
      } catch {
        if (!cancelled) setOffline(true);
      }
      setTick((t) => t + 1);
    };
    load();
    const id = setInterval(load, STATUS_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [services?.backend]);

  if (offline) {
    const starting = services && STARTING.includes(services.backend);
    const message = starting
      ? 'Starting Personal Memory...'
      : services?.backend === 'docker-stopped'
        ? "Search is paused because Docker Desktop isn't running. Open it to continue."
        : canManageServices()
          ? "Search isn't running. Open Settings and choose Run setup again."
          : "Search isn't running. Start it with docker compose up -d";
    return (
      <div style={styles.bar} data-testid="status-bar" role="status">
        <span style={styles.item} data-testid={starting ? 'status-starting' : 'status-offline'}>
          <span style={{ ...styles.dot, backgroundColor: starting ? COLORS.muted : COLORS.bad }} />
          {message}
        </span>
      </div>
    );
  }

  if (!status) {
    return <div style={styles.bar} data-testid="status-bar" role="status">Loading...</div>;
  }

  return (
    <div style={styles.bar} data-testid="status-bar" role="status">
      <span style={styles.item} data-testid="status-docs">
        <span style={{ ...styles.dot, backgroundColor: COLORS.good }} />
        {plural(status.total_docs, 'document')} indexed
      </span>
      <span data-testid="status-percent">
        {status.percent_indexed === null ? 'Nothing added yet' : `${status.percent_indexed}% indexed`}
      </span>
      <span data-testid="status-updated">Last updated {timeAgo(status.last_updated)}</span>
      <span data-testid="status-pending">{status.pending_jobs} in progress</span>
      <span data-testid="status-failed" style={status.failed_docs ? { color: COLORS.bad } : undefined}>
        {plural(status.failed_docs, 'error')}
      </span>
      <span data-testid="status-watched">
        {watched ? `Watching ${plural(watched, 'folder')}` : 'No folders watched'}
      </span>
    </div>
  );
}
