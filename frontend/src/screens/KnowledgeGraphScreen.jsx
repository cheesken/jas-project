import React from 'react';
import { COLORS } from '../ui';

const styles = {
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '40px',
    boxSizing: 'border-box',
    textAlign: 'center',
  },
  title: { fontSize: '24px', fontWeight: 600, color: COLORS.text, margin: '0 0 8px 0' },
  text: { fontSize: '15px', color: COLORS.muted, margin: 0, maxWidth: '440px', lineHeight: 1.5 },
};

export default function KnowledgeGraphScreen() {
  return (
    <div style={styles.main} data-testid="graph-screen">
      <h1 style={styles.title}>Knowledge Graph</h1>
      <p style={styles.text}>
        The interactive graph viewer is coming soon. People, places and organizations are already being
        extracted from everything you index.
      </p>
    </div>
  );
}
