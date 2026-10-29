import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, TextStyle, View, ViewStyle } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { FONT, PALETTE, RADIUS } from '../theme';

export type ActionVariant = 'filled' | 'tonal' | 'outline' | 'danger' | 'ghost';

const VARIANTS: Record<
  ActionVariant,
  { bg: string; border: string; fg: string; ripple: string }
> = {
  filled: { bg: PALETTE.primary, border: PALETTE.primary, fg: PALETTE.onPrimary, ripple: '#FFFFFF' },
  tonal: { bg: PALETTE.primaryContainer, border: 'transparent', fg: PALETTE.onPrimaryContainer, ripple: '#FFFFFF' },
  outline: { bg: 'transparent', border: PALETTE.outline, fg: PALETTE.text, ripple: PALETTE.primary },
  danger: { bg: PALETTE.danger, border: PALETTE.danger, fg: '#3B0000', ripple: '#000000' },
  ghost: { bg: 'transparent', border: 'transparent', fg: PALETTE.primary, ripple: PALETTE.primary },
};

type Props = {
  label: string;
  onPress?: () => void;
  icon?: keyof typeof MaterialCommunityIcons.glyphMap;
  variant?: ActionVariant;
  disabled?: boolean;
  loading?: boolean;
  style?: ViewStyle;
  labelStyle?: TextStyle;
  compact?: boolean;
  accessibilityHint?: string;
};

export default function ActionButton({
  label,
  onPress,
  icon,
  variant = 'filled',
  disabled,
  loading,
  style,
  labelStyle,
  compact,
  accessibilityHint,
}: Props) {
  const v = VARIANTS[variant];
  const inactive = disabled || loading;
  const fg = inactive ? PALETTE.textFaint : v.fg;

  return (
    <Pressable
      onPress={inactive ? undefined : onPress}
      disabled={inactive}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: !!inactive }}
      android_ripple={{ color: v.ripple, borderless: false }}
      style={({ pressed }) => [
        styles.base,
        compact && styles.compact,
        {
          backgroundColor: inactive ? PALETTE.surfaceHigh : v.bg,
          borderColor: inactive ? PALETTE.outlineSoft : v.border,
        },
        pressed && !inactive && styles.pressed,
        style,
      ]}
    >
      <View style={styles.content}>
        {loading ? (
          <ActivityIndicator size="small" color={fg} />
        ) : (
          !!icon && <MaterialCommunityIcons name={icon} size={compact ? 15 : 18} color={fg} />
        )}
        <Text
          style={[styles.label, compact && styles.labelCompact, { color: fg }, labelStyle]}
          numberOfLines={1}
        >
          {label}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 50,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  compact: { minHeight: 38, paddingVertical: 8, paddingHorizontal: 14 },
  pressed: { opacity: 0.86 },
  content: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  label: {
    fontFamily: FONT.sansSemiBold,
    fontSize: 14,
    letterSpacing: 0.1,
  },
  labelCompact: { fontSize: 12.5 },
});
