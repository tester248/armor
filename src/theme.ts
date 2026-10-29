import { MD3DarkTheme } from 'react-native-paper';
import type { MD3Theme } from 'react-native-paper';

/* ──────────────────────────────────────────────────────────────────────────
   ARMOR — "Blueprint Control"
   A Material 3 dark system for a shop-floor safety console.
   Deep blueprint ground, machined hairlines, IBM Plex, mono telemetry.
   ────────────────────────────────────────────────────────────────────────── */

export const PALETTE = {
  // ground
  bg: '#0B1016',
  surface: '#111A23',
  surfaceLow: '#131D27',
  surfaceContainer: '#17222D',
  surfaceHigh: '#1D2A36',
  surfaceHighest: '#243342',

  // ink
  text: '#E8EFF5',
  textMuted: '#A3B4C2',
  textFaint: '#71879A',

  // lines
  outline: '#33475A',
  outlineSoft: '#233342',

  // brand + semantics
  primary: '#6FB7FF',
  onPrimary: '#00243D',
  primaryContainer: '#0E4A75',
  onPrimaryContainer: '#CDE5FF',

  success: '#45D48A',
  successContainer: '#07301F',
  onSuccessContainer: '#A9F5CE',

  warning: '#E3B341',
  warningContainer: '#3B2A00',
  onWarningContainer: '#FFE08A',

  danger: '#FF6B6B',
  dangerContainer: '#4A0E12',
  onDangerContainer: '#FFD6D2',

  info: '#8FC7FF',
  infoContainer: '#0E2E4A',
  onInfoContainer: '#CDE5FF',
} as const;

export const STATUS = {
  OK: PALETTE.success,
  WARNING: PALETTE.warning,
  DANGER: PALETTE.danger,
  INFO: PALETTE.primary,
  MUTED: PALETTE.textMuted,
  NEUTRAL: '#8FA3B5',
};

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  '2xl': 32,
} as const;

export const RADIUS = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  pill: 999,
} as const;

export const FONT = {
  sans: 'IBMPlexSans_400Regular',
  sansMedium: 'IBMPlexSans_500Medium',
  sansSemiBold: 'IBMPlexSans_600SemiBold',
  sansBold: 'IBMPlexSans_700Bold',
  mono: 'IBMPlexMono_400Regular',
  monoMedium: 'IBMPlexMono_500Medium',
  monoSemiBold: 'IBMPlexMono_600SemiBold',
} as const;

const plexFonts = (base: MD3Theme['fonts']): MD3Theme['fonts'] => {
  const out: any = { ...base };
  (Object.keys(base) as (keyof MD3Theme['fonts'])[]).forEach((key) => {
    out[key] = { ...(base[key] as any), fontFamily: FONT.sans };
  });
  return out;
};

export const armorTheme: MD3Theme = {
  ...MD3DarkTheme,
  roundness: RADIUS.md,
  fonts: plexFonts(MD3DarkTheme.fonts),
  colors: {
    ...MD3DarkTheme.colors,
    primary: PALETTE.primary,
    onPrimary: PALETTE.onPrimary,
    primaryContainer: PALETTE.primaryContainer,
    onPrimaryContainer: PALETTE.onPrimaryContainer,

    secondary: '#8FB3D9',
    onSecondary: '#0B2438',
    secondaryContainer: '#1B3346',
    onSecondaryContainer: '#CFE4F7',

    tertiary: PALETTE.warning,
    onTertiary: '#3B2A00',
    tertiaryContainer: PALETTE.warningContainer,
    onTertiaryContainer: PALETTE.onWarningContainer,

    error: PALETTE.danger,
    onError: '#3B0000',
    errorContainer: PALETTE.dangerContainer,
    onErrorContainer: PALETTE.onDangerContainer,

    background: PALETTE.bg,
    onBackground: PALETTE.text,
    surface: PALETTE.surface,
    onSurface: PALETTE.text,
    surfaceVariant: PALETTE.surfaceContainer,
    onSurfaceVariant: PALETTE.textMuted,
    outline: PALETTE.outline,
    outlineVariant: PALETTE.outlineSoft,
    surfaceDisabled: 'rgba(232,239,245,0.10)',
    onSurfaceDisabled: 'rgba(232,239,245,0.38)',
    inverseSurface: PALETTE.text,
    inverseOnSurface: PALETTE.bg,
    inversePrimary: '#00497A',
    shadow: '#000000',
    scrim: '#000000',
    backdrop: 'rgba(11,16,22,0.6)',
  },
};

// Kept for imports elsewhere
export const armorDarkTheme = armorTheme;

/* React Navigation palette */
export const navigationTheme = {
  dark: true,
  colors: {
    primary: PALETTE.primary,
    background: PALETTE.bg,
    card: PALETTE.surface,
    text: PALETTE.text,
    border: PALETTE.outlineSoft,
    notification: PALETTE.danger,
  },
  fonts: {
    regular: { fontFamily: FONT.sans, fontWeight: '400' as const },
    medium: { fontFamily: FONT.sansMedium, fontWeight: '500' as const },
    bold: { fontFamily: FONT.sansSemiBold, fontWeight: '600' as const },
    heavy: { fontFamily: FONT.sansBold, fontWeight: '700' as const },
  },
};

/* Shared type styles */
export const TYPE = {
  display: { fontFamily: FONT.sansSemiBold, fontSize: 32, lineHeight: 38, letterSpacing: -0.6, color: PALETTE.text },
  headline: { fontFamily: FONT.sansSemiBold, fontSize: 24, lineHeight: 30, letterSpacing: -0.3, color: PALETTE.text },
  title: { fontFamily: FONT.sansSemiBold, fontSize: 18, lineHeight: 24, color: PALETTE.text },
  subtitle: { fontFamily: FONT.sansMedium, fontSize: 15, lineHeight: 21, color: PALETTE.text },
  body: { fontFamily: FONT.sans, fontSize: 14, lineHeight: 21, color: PALETTE.text },
  caption: { fontFamily: FONT.sans, fontSize: 12, lineHeight: 17, color: PALETTE.textMuted },
  label: { fontFamily: FONT.sansMedium, fontSize: 11, lineHeight: 15, letterSpacing: 0.4, color: PALETTE.textMuted },
  dataXL: { fontFamily: FONT.monoSemiBold, fontSize: 34, lineHeight: 38, letterSpacing: -0.8, color: PALETTE.text },
  dataL: { fontFamily: FONT.monoSemiBold, fontSize: 28, lineHeight: 32, letterSpacing: -0.5, color: PALETTE.text },
  dataM: { fontFamily: FONT.monoMedium, fontSize: 18, lineHeight: 23, color: PALETTE.text },
  dataS: { fontFamily: FONT.mono, fontSize: 13, lineHeight: 18, color: PALETTE.textMuted },
} as const;

export const SURFACE_STYLE = {
  backgroundColor: PALETTE.surface,
  borderWidth: 1,
  borderColor: PALETTE.outlineSoft,
  borderRadius: RADIUS.lg,
} as const;
