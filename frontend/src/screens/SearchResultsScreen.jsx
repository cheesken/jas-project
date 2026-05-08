import React, { useState, useEffect, useCallback } from 'react';
import SearchBar from '../components/SearchBar';
import ResultCard from '../components/ResultCard';
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
    padding: '40px',
    boxSizing: 'border-box',
    overflowY: 'auto',
  },
  searchWrapper: {
    marginBottom: '24px',
  },
  responseBox: {
    backgroundColor: '#FFFFFF',
    border: '1px solid #D1CBC3',
    borderRadius: '8px',
    padding: '16px',
    marginBottom: '20px',
    fontSize: '15px',
    color: '#1F1B16',
    fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    lineHeight: 1.5,
  },
  spinner: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    padding: '60px 0',
    fontSize: '16px',
    color: '#6B6259',
  },
  errorMessage: {
    textAlign: 'center',
    padding: '40px 0',
    fontSize: '15px',
    color: '#6B6259',
  },
  resultsList: {
    display: 'flex',
    flexDirection: 'column',
  },
};

export default function SearchResultsScreen({ query, onSearch, onGoHome }) {
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [results, setResults] = useState([]);
  const [response, setResponse] = useState('');
  const [error, setError] = useState(null);
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((message, type) => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, message, type }]);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setStreaming(false);
    setError(null);
    setResults([]);
    setResponse('');

    const controller = new AbortController();

    fetch(`http://localhost:8000/query/stream?q=${encodeURIComponent(query)}&top_k=10`, {
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) throw new Error('Backend error');
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done || cancelled) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop();

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            let data;
            try { data = JSON.parse(line.slice(6)); } catch { continue; }

            if (data.type === 'results') {
              setResults(data.results);
              setLoading(false);
              setStreaming(true);
            } else if (data.type === 'token') {
              setResponse((prev) => prev + data.token);
            } else if (data.type === 'done') {
              setStreaming(false);
            } else if (data.type === 'error') {
              setResponse(data.message);
              setLoading(false);
              setStreaming(false);
            }
          }
        }
      })
      .catch((err) => {
        if (cancelled || err.name === 'AbortError') return;
        setError('Could not reach the backend. Is it running?');
        setLoading(false);
        setStreaming(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [query]);

  const handleUpload = async () => {
    let filePath;
    if (window.electronAPI) {
      filePath = await window.electronAPI.openPdfFile();
    } else {
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
        <div style={styles.searchWrapper}>
          <SearchBar initialQuery={query} onSearch={onSearch} />
        </div>

        {loading && <div style={styles.spinner}>Searching...</div>}

        {error && <div style={styles.errorMessage}>{error}</div>}

        {!loading && !error && (
          <>
            {(response || streaming) && (
              <div style={styles.responseBox}>
                {response}
                {streaming && <span style={{ opacity: 0.5 }}>▋</span>}
              </div>
            )}

            {results.length > 0 ? (
              <div style={styles.resultsList}>
                {results.map((r) => (
                  <ResultCard
                    key={r.chunk_id}
                    content={r.content}
                    fileName={r.file_name}
                    sourceType={r.source_type}
                    lastModified={r.last_modified}
                    score={r.score}
                  />
                ))}
              </div>
            ) : (
              !response && (
                <div style={styles.errorMessage}>No results found.</div>
              )
            )}
          </>
        )}
      </div>
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
