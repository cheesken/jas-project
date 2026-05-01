import React from 'react';

const styles = {
  card: {
    backgroundColor: '#FFFFFF',
    borderLeft: '4px solid #7B4A27',
    padding: '16px',
    marginBottom: '12px',
    fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    color: '#1F1B16',
    boxSizing: 'border-box',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '8px',
    gap: '12px',
  },
  badge: {
    backgroundColor: '#EAE7E1',
    color: '#1F1B16',
    fontSize: '11px',
    padding: '2px 8px',
    borderRadius: '999px',
    whiteSpace: 'nowrap',
  },
  score: {
    color: '#6B6259',
    fontSize: '12px',
    whiteSpace: 'nowrap',
  },
  fileName: {
    fontSize: '16px',
    fontWeight: 600,
    color: '#1F1B16',
    margin: '0 0 6px 0',
    wordBreak: 'break-word',
  },
  excerpt: {
    fontSize: '14px',
    color: '#1F1B16',
    margin: '0 0 8px 0',
    display: '-webkit-box',
    WebkitLineClamp: 3,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  date: {
    fontSize: '12px',
    color: '#6B6259',
  },
};

const formatDate = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const formatted = new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
  }).format(d);
  return `Modified: ${formatted}`;
};

export default function ResultCard({
  content,
  fileName,
  sourceType,
  lastModified,
  score,
}) {
  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <span style={styles.badge}>{sourceType}</span>
        <span style={styles.score}>Score: {Number(score).toFixed(2)}</span>
      </div>
      <h3 style={styles.fileName}>{fileName}</h3>
      <p style={styles.excerpt}>{content}</p>
      <div style={styles.date}>{formatDate(lastModified)}</div>
    </div>
  );
}
