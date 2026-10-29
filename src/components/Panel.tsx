import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';

export function Panel({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.panel, style]}>{children}</View>;
}

export function SectionHeader({
  title,
  icon,
  right,
  style,
}: {
  title: string;
  icon?: keyof typeof MaterialCommunityIcons.glyphMap;
  right?: React.ReactNode;
  style?: ViewStyle;
}) {
  return (
    <View style={[styles.section, style]}>
      <View style={styles.sectionLeft}>
        {!!icon && <MaterialCommunityIcons name={icon} size={16} color={PALETTE.primary} />}
        <Text style={styles.sectionTitle}>{title}</Text>
      </View>
      {right}
    </View>
  );
}

export function Row({
  label,
  value,
  valueColor,
  mono,
}: {
  label: string;
  value: string;
  valueColor?: string;
  mono?: boolean;
}) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text
        style={[
          styles.rowValue,
          mono && { fontFamily: FONT.mono },
          valueColor ? { color: valueColor } : null,
        ]}
        numberOfLines={1}
      >
        {value}
      </Text>
    </View>
  );
}

export function Divider() {
  return <View style={styles.divider} />;
}

export function EmptyState({
  icon,
  title,
  body,
}: {
  icon: keyof typeof MaterialCommunityIcons.glyphMap;
  title: string;
  body?: string;
}) {
  return (
    <View style={styles.empty}>
      <MaterialCommunityIcons name={icon} size={28} color={PALETTE.textFaint} />
      <Text style={styles.emptyTitle}>{title}</Text>
      {!!body && <Text style={styles.emptyBody}>{body}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    borderRadius: RADIUS.lg,
    padding: SPACING.lg,
  },
  section: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: SPACING.sm,
    marginTop: SPACING.xs,
  },
  sectionLeft: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  sectionTitle: {
    fontFamily: FONT.sansSemiBold,
    fontSize: 13,
    letterSpacing: 0.2,
    color: PALETTE.text,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 7,
    gap: 12,
  },
  rowLabel: { fontFamily: FONT.sans, fontSize: 13, color: PALETTE.textMuted, flexShrink: 1 },
  rowValue: {
    fontFamily: FONT.sansMedium,
    fontSize: 13,
    color: PALETTE.text,
    textAlign: 'right',
    flexShrink: 1,
  },
  divider: { height: 1, backgroundColor: PALETTE.outlineSoft },
  empty: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: SPACING['2xl'],
    paddingHorizontal: SPACING.lg,
  },
  emptyTitle: {
    fontFamily: FONT.sansMedium,
    fontSize: 14,
    color: PALETTE.textMuted,
    marginTop: SPACING.sm,
    textAlign: 'center',
  },
  emptyBody: {
    fontFamily: FONT.sans,
    fontSize: 12,
    lineHeight: 18,
    color: PALETTE.textFaint,
    marginTop: 4,
    textAlign: 'center',
    maxWidth: 280,
  },
});
