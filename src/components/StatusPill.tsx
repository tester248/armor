import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { FONT, PALETTE, RADIUS } from '../theme';

export type Tone = 'ok' | 'warn' | 'danger' | 'info' | 'neutral';

const TONES: Record<Tone, { bg: string; border: string; fg: string }> = {
  ok: { bg: 'rgba(69,212,138,0.10)', border: 'rgba(69,212,138,0.32)', fg: PALETTE.success },
  warn: { bg: 'rgba(227,179,65,0.12)', border: 'rgba(227,179,65,0.34)', fg: PALETTE.warning },
  danger: { bg: 'rgba(255,107,107,0.12)', border: 'rgba(255,107,107,0.36)', fg: PALETTE.danger },
  info: { bg: 'rgba(111,183,255,0.10)', border: 'rgba(111,183,255,0.32)', fg: PALETTE.primary },
  neutral: { bg: 'rgba(163,180,194,0.08)', border: 'rgba(163,180,194,0.24)', fg: PALETTE.textMuted },
};

type Props = {
  label: string;
  value: string;
  icon: keyof typeof MaterialCommunityIcons.glyphMap;
  tone?: Tone;
  compact?: boolean;
};

/** State is encoded icon + label + colour, never colour alone. */
export default function StatusPill({ label, value, icon, tone = 'neutral', compact }: Props) {
  const t = TONES[tone];
  return (
    <View
      style={[
        styles.wrap,
        { backgroundColor: t.bg, borderColor: t.border },
        compact && styles.compact,
      ]}
    >
      <View style={styles.top}>
        <MaterialCommunityIcons name={icon} size={compact ? 15 : 17} color={t.fg} />
        <Text style={[styles.label, compact && { fontSize: 9 }]} numberOfLines={1}>
          {label}
        </Text>
        <View style={[styles.dot, { backgroundColor: t.fg }]} />
      </View>
      <Text style={[styles.value, { color: t.fg }, compact && { fontSize: 12 }]} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 9,
    minWidth: 0,
  },
  compact: { paddingHorizontal: 8, paddingVertical: 7 },
  top: { flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: 5 },
  label: {
    fontFamily: FONT.sansMedium,
    fontSize: 10,
    letterSpacing: 0.5,
    color: PALETTE.textMuted,
    flex: 1,
  },
  dot: { width: 5, height: 5, borderRadius: 3 },
  value: {
    fontFamily: FONT.sansSemiBold,
    fontSize: 14,
    letterSpacing: 0.2,
  },
});
