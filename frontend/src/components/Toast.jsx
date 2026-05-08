import React, { useEffect } from 'react';

const typeColors = {
  info: '#7B4A27',
  success: '#3a7d44',
  error: '#c0392b',
};

const styles = {
  container: {
    position: 'fixed',
    bottom: '24px',
    right: '24px',
    zIndex: 9999,
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  toast: {
    padding: '12px 20px',
    borderRadius: '8px',
    color: '#FFFFFF',
    fontSize: '14px',
    fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
    maxWidth: '360px',
    animation: 'fadeIn 0.2s ease-in',
  },
};

export function ToastContainer({ toasts, onDismiss }) {
  return (
    <div style={styles.container}>
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), 4000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  return (
    <div
      style={{
        ...styles.toast,
        backgroundColor: typeColors[toast.type] || typeColors.info,
      }}
      onClick={() => onDismiss(toast.id)}
    >
      {toast.message}
    </div>
  );
}
