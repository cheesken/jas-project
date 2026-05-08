import React, { useState } from 'react';

const styles = {
  form: {
    display: 'flex',
    gap: '8px',
    width: '100%',
    maxWidth: '560px',
  },
  input: {
    flex: 1,
    padding: '12px 16px',
    fontSize: '15px',
    fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    border: '1px solid #D1CBC3',
    borderRadius: '8px',
    backgroundColor: '#FFFFFF',
    color: '#1F1B16',
    outline: 'none',
  },
  button: {
    padding: '12px 24px',
    fontSize: '15px',
    fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    fontWeight: 600,
    backgroundColor: '#7B4A27',
    color: '#FFFFFF',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
  },
};

export default function SearchBar({ initialQuery = '', onSearch }) {
  const [value, setValue] = useState(initialQuery);

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (trimmed) {
      onSearch(trimmed);
    }
  };

  return (
    <form style={styles.form} onSubmit={handleSubmit}>
      <input
        style={styles.input}
        type="text"
        placeholder="Search your memory..."
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button style={styles.button} type="submit">
        Search
      </button>
    </form>
  );
}
