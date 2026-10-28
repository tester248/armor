import { MD3DarkTheme, MD3LightTheme } from 'react-native-paper';

// ARMOR dark industrial theme — matches the Streamlit dashboard palette
export const armorDarkTheme = {
  ...MD3DarkTheme,
  colors: {
    ...MD3DarkTheme.colors,
    primary: '#06b6d4',
    primaryContainer: '#164e63',
    secondary: '#10b981',
    secondaryContainer: '#064e3b',
    tertiary: '#f59e0b',
    tertiaryContainer: '#78350f',
    error: '#ef4444',
    errorContainer: '#7f1d1d',
    background: '#0b0f19',
    surface: '#121a2b',
    surfaceVariant: '#1e293b',
    onBackground: '#f8fafc',
    onSurface: '#f8fafc',
    onSurfaceVariant: '#94a3b8',
    outline: '#334155',
    outlineVariant: '#1e293b',
    elevation: {
      level0: 'transparent',
      level1: '#121a2b',
      level2: '#1e293b',
      level3: '#334155',
    },
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
