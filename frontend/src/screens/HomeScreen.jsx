import React, { useState, useCallback } from 'react';
import SearchBar from '../components/SearchBar';
import { ToastContainer } from '../components/Toast';

let toastId = 0;

const styles = {
  layout: {
    display: 'flex',
    height: '100vh',
    width: '100vw',
  },
  sidebar: {
    width: '200px',
    minWidth: '200px',
    backgroundColor: '#EAE7E1',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'flex-end',
    padding: '16px',
    boxSizing: 'border-box',
  },
  uploadButton: {
    padding: '10px 16px',
    fontSize: '14px',
    fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    fontWeight: 600,
    backgroundColor: '#7B4A27',
    color: '#FFFFFF',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    width: '100%',
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '40px',
    boxSizing: 'border-box',
  },
  greeting: {
    fontSize: '28px',
    fontWeight: 600,
    color: '#1F1B16',
    margin: '0 0 8px 0',
  },
  subtext: {
    fontSize: '16px',
    color: '#6B6259',
    margin: '0 0 32px 0',
  },
  footer: {
    fontSize: '13px',
    color: '#6B6259',
    marginTop: '32px',
  },
};

export default function HomeScreen({ onSearch }) {
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((message, type) => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, message, type }]);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const handleUpload = async () => {
    let filePath;
    if (window.electronAPI) {
      filePath = await window.electronAPI.openPdfFile();
    } else {
      // Fallback for browser dev: prompt for path
      filePath = prompt('Enter PDF file path (Electron not available):');
    }
    if (!filePath) return;

    const fileName = filePath.split('/').pop();
    showToast(`Uploading ${fileName}...`, 'info');

    try {
      const res = await fetch('http://localhost:8000/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: filePath, file_type: 'pdf' }),
      });
      if (res.status === 201) {
        showToast(`${fileName} is being indexed.`, 'success');
      } else if (res.status === 409) {
        showToast(`${fileName} is already indexed.`, 'info');
      } else {
        showToast(`Failed to upload ${fileName}. Please try again.`, 'error');
      }
    } catch (err) {
      showToast(`Failed to upload ${fileName}. Please try again.`, 'error');
    }
  };

  return (
    <div style={styles.layout}>
      <div style={styles.sidebar}>
        <button style={styles.uploadButton} onClick={handleUpload}>
          Upload Files
        </button>
      </div>
      <div style={styles.main}>
        <h1 style={styles.greeting}>Hello, there.</h1>
        <p style={styles.subtext}>What's on your mind today?</p>
        <SearchBar onSearch={onSearch} />
        <p style={styles.footer}>Everything stays on your device. Always.</p>
      </div>
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
