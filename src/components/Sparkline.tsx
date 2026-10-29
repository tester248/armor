import React from 'react';
import { StyleSheet, View } from 'react-native';
import { PALETTE, RADIUS } from '../theme';

export default function Sparkline({
  values,
  color = PALETTE.primary,
  height = 22,
  bars = 16,
}: {
  values: number[];
  color?: string;
  height?: number;
  bars?: number;
}) {
  const slice = values.slice(-bars);
  const padded =
    slice.length >= bars
      ? slice
      : Array.from({ length: bars - slice.length }, () => slice[0] ?? 0).concat(slice);
  const min = Math.min(...padded);
  const max = Math.max(...padded);
  const span = max - min || 1;

  return (
    <View style={[styles.wrap, { height }]}>
      {padded.map((v, i) => {
        const h = 3 + ((v - min) / span) * (height - 3);
        return (
          <View
            key={`${i}-${v}`}
            style={[
              styles.bar,
              {
                height: h,
                backgroundColor: color,
                opacity: 0.32 + (i / padded.length) * 0.5,
              },
            ]}
          />
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', alignItems: 'flex-end', gap: 2 },
  bar: { flex: 1, borderRadius: RADIUS.sm / 2, minHeight: 3 },
});
