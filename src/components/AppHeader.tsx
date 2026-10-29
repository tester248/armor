import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';

type Props = {
  title: string;
  subtitle?: string;
  connected?: boolean;
  rightIcon?: keyof typeof MaterialCommunityIcons.glyphMap;
  onRightPress?: () => void;
  rightLabel?: string;
};

export default function AppHeader({
  title,
  subtitle,
  connected,
  rightIcon,
  onRightPress,
  rightLabel,
}: Props) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.wrap, { paddingTop: insets.top + 8 }]}>
      <View style={styles.mark}>
        <MaterialCommunityIcons name="shield-half-full" size={22} color={PALETTE.primary} />
      </View>
      <View style={styles.titles}>
        <Text style={styles.title} numberOfLines={1}>
          {title}
        </Text>
        {!!subtitle && (
          <Text style={styles.subtitle} numberOfLines={1}>
            {subtitle}
          </Text>
        )}
      </View>
      {connected !== undefined && (
        <View style={[styles.live, !connected && styles.liveOff]}>
          <View style={[styles.dot, { backgroundColor: connected ? PALETTE.success : PALETTE.danger }]} />
          <Text style={[styles.liveText, !connected && { color: PALETTE.danger }]}>
            {connected ? 'LIVE' : 'OFFLINE'}
          </Text>
        </View>
      )}
      {!!rightIcon && (
        <View style={styles.action}>
          <MaterialCommunityIcons
            name={rightIcon}
            size={22}
            color={PALETTE.textMuted}
            onPress={onRightPress}
            accessibilityLabel={rightLabel}
          />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.lg,
    paddingBottom: SPACING.md,
    backgroundColor: PALETTE.bg,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.outlineSoft,
  },
  mark: {
    width: 38,
    height: 38,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: PALETTE.outline,
    backgroundColor: PALETTE.surfaceContainer,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: SPACING.md,
  },
  titles: { flex: 1, minWidth: 0 },
  title: {
    fontFamily: FONT.sansSemiBold,
    fontSize: 19,
    lineHeight: 24,
    letterSpacing: -0.2,
    color: PALETTE.text,
  },
  subtitle: {
    fontFamily: FONT.sans,
    fontSize: 11,
    lineHeight: 15,
    color: PALETTE.textMuted,
    marginTop: 1,
  },
  live: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
    borderColor: 'rgba(69,212,138,0.35)',
    backgroundColor: 'rgba(69,212,138,0.10)',
  },
  liveOff: {
    borderColor: 'rgba(255,107,107,0.35)',
    backgroundColor: 'rgba(255,107,107,0.10)',
  },
  dot: { width: 6, height: 6, borderRadius: 3, marginRight: 6 },
  liveText: {
    fontFamily: FONT.sansSemiBold,
    fontSize: 10,
    letterSpacing: 1,
    color: PALETTE.success,
  },
  action: {
    marginLeft: SPACING.sm,
    width: 38,
    height: 38,
    borderRadius: RADIUS.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    backgroundColor: PALETTE.surface,
  },
});
