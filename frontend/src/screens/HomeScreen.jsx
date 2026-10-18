import React from 'react';
import SearchBar from '../components/SearchBar';

const styles = {
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
  return (
    <div style={styles.main} data-testid="home-screen">
      <h1 style={styles.greeting}>Hello, there.</h1>
      <p style={styles.subtext}>What's on your mind today?</p>
      <SearchBar onSearch={onSearch} />
      <p style={styles.footer}>Everything stays on your device. Always.</p>
    </div>
  );
}
