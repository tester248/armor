import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';
import Sparkline from './Sparkline';

type Props = {
  label: string;
  value: string;
  unit?: string;
  icon: keyof typeof MaterialCommunityIcons.glyphMap;
  accent?: string;
  footerLeft?: string;
  footerRight?: string;
  footerRightColor?: string;
  history?: number[];
  style?: object;
};

export default function MetricCard({
  label,
  value,
  unit,
  icon,
  accent = PALETTE.primary,
  footerLeft,
  footerRight,
  footerRightColor,
  history,
  style,
}: Props) {
  return (
    <View style={[styles.card, style]}>
      <View style={styles.head}>
        <Text style={styles.label} numberOfLines={1}>
          {label}
        </Text>
        <MaterialCommunityIcons name={icon} size={16} color={accent} />
      </View>
      <View style={styles.valueRow}>
        <Text style={styles.value} numberOfLines={1} adjustsFontSizeToFit>
          {value}
        </Text>
        {!!unit && <Text style={styles.unit}>{unit}</Text>}
      </View>
      {!!history && history.length > 1 && (
        <View style={styles.spark}>
          <Sparkline values={history} color={accent} height={18} />
        </View>
      )}
      {(!!footerLeft || !!footerRight) && (
        <View style={styles.footer}>
          <Text style={styles.footerText} numberOfLines={1}>
            {footerLeft || ''}
          </Text>
          <Text
            style={[styles.footerText, footerRightColor ? { color: footerRightColor } : null]}
            numberOfLines={1}
          >
            {footerRight || ''}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    minWidth: 0,
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    borderRadius: RADIUS.lg,
    padding: SPACING.md,
  },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 6 },
  label: { fontFamily: FONT.sansMedium, fontSize: 11, letterSpacing: 0.4, color: PALETTE.textMuted, flex: 1 },
  valueRow: { flexDirection: 'row', alignItems: 'baseline', marginTop: 6, gap: 4 },
  value: {
    fontFamily: FONT.monoSemiBold,
    fontSize: 24,
    lineHeight: 28,
    letterSpacing: -0.6,
    color: PALETTE.text,
    flexShrink: 1,
  },
  unit: { fontFamily: FONT.mono, fontSize: 12, color: PALETTE.textMuted },
  spark: { marginTop: 7 },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 7,
    gap: 8,
  },
  footerText: { fontFamily: FONT.mono, fontSize: 10, color: PALETTE.textFaint, flexShrink: 1 },
});
