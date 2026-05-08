import React, { useState } from 'react';
import HomeScreen from './screens/HomeScreen';
import SearchResultsScreen from './screens/SearchResultsScreen';

const globalStyles = {
  margin: 0,
  padding: 0,
  width: '100vw',
  height: '100vh',
  fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
  backgroundColor: '#F2EFE9',
  color: '#1F1B16',
  overflow: 'hidden',
};

export default function App() {
  const [screen, setScreen] = useState('home');
  const [query, setQuery] = useState('');

  const handleSearch = (q) => {
    setQuery(q);
    setScreen('results');
  };

  const handleGoHome = () => {
    setQuery('');
    setScreen('home');
  };

  return (
    <div style={globalStyles}>
      {screen === 'home' ? (
        <HomeScreen onSearch={handleSearch} />
      ) : (
        <SearchResultsScreen
          query={query}
          onSearch={handleSearch}
          onGoHome={handleGoHome}
        />
      )}
    </div>
  );
}
