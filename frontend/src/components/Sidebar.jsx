import React from 'react';
import { uploadFile, importChromeHistory } from '../ingest';
import { COLORS, FONT, buttons } from '../ui';

export const NAV_ITEMS = [
  { id: 'search', label: 'Search' },
  { id: 'graph', label: 'Knowledge Graph' },
  { id: 'settings', label: 'Settings' },
];

const styles = {
  sidebar: {
    width: '200px',
    minWidth: '200px',
    backgroundColor: COLORS.sidebar,
    display: 'flex',
    flexDirection: 'column',
    padding: '48px 16px 16px',
    boxSizing: 'border-box',
    gap: '4px',
  },
  navItem: {
    textAlign: 'left',
    padding: '8px 12px',
    fontSize: '14px',
    fontFamily: FONT,
    color: COLORS.text,
    backgroundColor: 'transparent',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
  },
  navItemActive: {
    backgroundColor: '#DDD8D0',
    fontWeight: 600,
  },
  spacer: { flex: 1 },
  bottom: { display: 'flex', flexDirection: 'column', gap: '8px' },
};

export default function Sidebar({ active, onNavigate, showToast }) {
  return (
    <nav style={styles.sidebar} aria-label="Main">
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          data-testid={`nav-${item.id}`}
          aria-current={active === item.id ? 'page' : undefined}
          style={{ ...styles.navItem, ...(active === item.id ? styles.navItemActive : {}) }}
          onClick={() => onNavigate(item.id)}
        >
          {item.label}
        </button>
      ))}
      <div style={styles.spacer} />
      <div style={styles.bottom}>
        <button style={buttons.secondary} onClick={() => importChromeHistory(showToast)}>
          Import Chrome History
        </button>
        <button style={buttons.primary} onClick={() => uploadFile(showToast)}>
          Upload Files
        </button>
      </div>
    </nav>
  );
}
