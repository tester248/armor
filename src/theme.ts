import { MD3DarkTheme } from 'react-native-paper';

// ARMOR dark industrial theme — matches Streamlit dashboard palette
// All surfaces are dark; text/icons use high-contrast colors
export const armorDarkTheme = {
  ...MD3DarkTheme,
  colors: {
    ...MD3DarkTheme.colors,
    primary: '#06b6d4',        // cyan — primary actions
    primaryContainer: '#164e63',
    secondary: '#10b981',      // green — success states
    secondaryContainer: '#064e3b',
    tertiary: '#f59e0b',       // amber — warnings
    tertiaryContainer: '#78350f',
    error: '#ef4444',          // red — danger/lockout
    errorContainer: '#7f1d1d',
    background: '#0a0e17',     // near-black background
    surface: '#121a2b',        // card background
    surfaceVariant: '#1e293b', // slightly elevated surface
    onBackground: '#f8fafc',   // white text on dark bg
    onSurface: '#f8fafc',      // white text on dark surface
    onSurfaceVariant: '#cbd5e1', // muted text on surface
    outline: '#334155',        // subtle borders
    outlineVariant: '#1e293b',
  },
  roundness: 8,
};

export const armorTheme = armorDarkTheme;

// Status colors for telemetry indicators
export const STATUS = {
  OK: '#10b981',
  WARNING: '#f59e0b',
  DANGER: '#ef4444',
  INFO: '#06b6d4',
  MUTED: '#94a3b8',
};

// Common spacing
export const SPACING = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
};
