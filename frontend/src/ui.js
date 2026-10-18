export const FONT = "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif";

export const COLORS = {
  page: '#F2EFE9',
  sidebar: '#EAE7E1',
  card: '#FFFFFF',
  border: '#D1CBC3',
  text: '#1F1B16',
  muted: '#6B6259',
  accent: '#7B4A27',
  good: '#3a7d44',
  bad: '#c0392b',
  dangerSoft: '#F7E6E3',
};

const buttonBase = {
  padding: '10px 16px',
  fontSize: '14px',
  fontFamily: FONT,
  fontWeight: 600,
  borderRadius: '8px',
  cursor: 'pointer',
};

export const buttons = {
  primary: { ...buttonBase, backgroundColor: COLORS.accent, color: '#FFFFFF', border: 'none' },
  secondary: { ...buttonBase, backgroundColor: 'transparent', color: COLORS.accent, border: `1px solid ${COLORS.accent}` },
  danger: { ...buttonBase, backgroundColor: COLORS.bad, color: '#FFFFFF', border: 'none' },
  small: { ...buttonBase, padding: '4px 10px', fontSize: '12px', backgroundColor: 'transparent', color: COLORS.bad, border: `1px solid ${COLORS.bad}` },
  link: { ...buttonBase, padding: 0, backgroundColor: 'transparent', color: COLORS.muted, border: 'none', fontWeight: 500, textDecoration: 'underline' },
};
