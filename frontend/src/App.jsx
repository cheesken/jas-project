import React, { useCallback, useState } from 'react';
import HomeScreen from './screens/HomeScreen';
import SearchResultsScreen from './screens/SearchResultsScreen';
import KnowledgeGraphScreen from './screens/KnowledgeGraphScreen';
import SettingsScreen from './screens/SettingsScreen';
import OnboardingScreen from './screens/OnboardingScreen';
import Sidebar from './components/Sidebar';
import StatusBar from './components/StatusBar';
import { ToastContainer } from './components/Toast';
import { COLORS, FONT } from './ui';

const ONBOARDING_KEY = 'onboardingComplete';

const styles = {
  app: {
    margin: 0,
    padding: 0,
    width: '100vw',
    height: '100vh',
    fontFamily: FONT,
    backgroundColor: COLORS.page,
    color: COLORS.text,
    overflow: 'hidden',
  },
  layout: { display: 'flex', height: '100%', width: '100%' },
  column: { flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' },
  content: { flex: 1, minHeight: 0, display: 'flex' },
};

function readOnboarded() {
  if (new URLSearchParams(window.location.search).has('skipOnboarding')) return true;
  try {
    return localStorage.getItem(ONBOARDING_KEY) === '1';
  } catch {
    return true;
  }
}

let toastId = 0;

export default function App() {
  const [onboarded, setOnboarded] = useState(readOnboarded);
  const [tab, setTab] = useState('search');
  const [query, setQuery] = useState('');
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((message, type) => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, message, type }]);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const finishOnboarding = () => {
    try {
      localStorage.setItem(ONBOARDING_KEY, '1');
    } catch {}
    setOnboarded(true);
    setTab('search');
  };

  const restartOnboarding = () => {
    try {
      localStorage.removeItem(ONBOARDING_KEY);
    } catch {}
    setOnboarded(false);
  };

  const handleSearch = (q) => {
    setQuery(q);
    setTab('search');
  };

  const navigate = (id) => {
    if (id === 'search' && tab === 'search') setQuery('');
    setTab(id);
  };

  return (
    <div style={styles.app}>
      {!onboarded ? (
        <OnboardingScreen onFinish={finishOnboarding} showToast={showToast} />
      ) : (
        <div style={styles.layout}>
          <Sidebar active={tab} onNavigate={navigate} showToast={showToast} />
          <div style={styles.column}>
            <main style={styles.content}>
              <div style={{ ...styles.content, display: tab === 'search' ? 'flex' : 'none' }}>
                {query ? (
                  <SearchResultsScreen query={query} onSearch={handleSearch} />
                ) : (
                  <HomeScreen onSearch={handleSearch} />
                )}
              </div>
              {tab === 'graph' && <KnowledgeGraphScreen />}
              {tab === 'settings' && <SettingsScreen showToast={showToast} onRestartSetup={restartOnboarding} />}
            </main>
            <StatusBar />
          </div>
        </div>
      )}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
