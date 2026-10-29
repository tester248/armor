import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { Panel } from './Panel';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';
import { num } from '../utils/format';

/* ──────────────────────────────────────────────────────────────────────────
   Trend chart — mobile port of the dashboard's chart tabs.
   One metric at a time keeps the axis honest on a phone-width panel.
   ────────────────────────────────────────────────────────────────────────── */

type MetricKey = 'rms' | 'current_ma' | 'voltage_v' | 'temperature_c';

const METRICS: {
  key: MetricKey;
  label: string;
  short: string;
  unit: string;
  digits: number;
  color: string;
  icon: keyof typeof MaterialCommunityIcons.glyphMap;
}[] = [
  {
    key: 'rms',
    label: 'Vibration',
    short: 'RMS',
    unit: 'g',
    digits: 3,
    color: PALETTE.primary,
    icon: 'waveform',
  },
  {
    key: 'current_ma',
    label: 'Current',
    short: 'INA219',
    unit: 'mA',
    digits: 1,
    color: PALETTE.info,
    icon: 'current-dc',
  },
  {
    key: 'voltage_v',
    label: 'Voltage',
    short: '12 V rail',
    unit: 'V',
    digits: 2,
    color: PALETTE.success,
    icon: 'flash-outline',
  },
  {
    key: 'temperature_c',
    label: 'Temp',
    short: 'DS18B20',
    unit: '°C',
    digits: 1,
    color: PALETTE.warning,
    icon: 'thermometer',
  },
];

const BARS = 26;
const CHART_HEIGHT = 84;

export default function TrendChart({ samples }: { samples: any[] }) {
  const [metric, setMetric] = useState<MetricKey>('rms');
  const active = METRICS.find((m) => m.key === metric)!;

  const series = useMemo(() => {
    const values = samples
      .map((s) => Number(s?.[metric]))
      .filter((n) => Number.isFinite(n))
      .slice(-BARS);
    if (values.length === 0) return [];
    return values;
  }, [samples, metric]);

  const stats = useMemo(() => {
    if (series.length === 0) return null;
    const min = Math.min(...series);
    const max = Math.max(...series);
    const avg = series.reduce((a, b) => a + b, 0) / series.length;
    return { min, max, avg, last: series[series.length - 1] };
  }, [series]);

  const span = stats ? stats.max - stats.min || Math.max(stats.max * 0.1, 0.001) : 1;

  return (
    <Panel style={{ gap: SPACING.md }}>
      <View style={styles.tabs}>
        {METRICS.map((m) => {
          const on = m.key === metric;
          return (
            <Pressable
              key={m.key}
              onPress={() => setMetric(m.key)}
              accessibilityRole="tab"
              accessibilityState={{ selected: on }}
              style={[styles.tab, on && { backgroundColor: PALETTE.primaryContainer, borderColor: 'rgba(111,183,255,0.45)' }]}
            >
              <MaterialCommunityIcons
                name={m.icon}
                size={13}
                color={on ? PALETTE.onPrimaryContainer : PALETTE.textFaint}
              />
              <Text style={[styles.tabText, on && { color: PALETTE.onPrimaryContainer }]}>
                {m.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.readout}>
        <Text style={styles.readoutValue}>{num(stats?.last, active.digits)}</Text>
        <Text style={styles.readoutUnit}>{active.unit}</Text>
        <Text style={styles.readoutMeta}>
          {active.short} · last {series.length} of {BARS}
        </Text>
      </View>

      <View style={styles.chart}>
        {stats && (
          <View
            style={[
              styles.avgLine,
              {
                bottom:
                  4 + ((stats.avg - stats.min) / span) * (CHART_HEIGHT - 8),
              },
            ]}
          />
        )}
        <View style={styles.bars}>
          {series.length === 0 ? (
            <Text style={styles.empty}>No samples for this channel yet.</Text>
          ) : (
            series.map((v, i) => {
              const h = 4 + ((v - (stats?.min ?? 0)) / span) * (CHART_HEIGHT - 8);
              return (
                <View
                  key={`${metric}-${i}`}
                  style={[
                    styles.bar,
                    {
                      height: h,
                      backgroundColor: active.color,
                      opacity: 0.34 + (i / series.length) * 0.58,
                    },
                  ]}
                />
              );
            })
          )}
        </View>
      </View>

      <View style={styles.footer}>
        <Text style={styles.footItem}>min {num(stats?.min, active.digits)}</Text>
        <Text style={styles.footItem}>avg {num(stats?.avg, active.digits)}</Text>
        <Text style={styles.footItem}>max {num(stats?.max, active.digits)}</Text>
        <Text style={[styles.footItem, { color: PALETTE.textFaint }]}>
          {stats ? `${active.unit} · rolling` : '--'}
        </Text>
      </View>
    </Panel>
  );
}

const styles = StyleSheet.create({
  tabs: { flexDirection: 'row', gap: 6 },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: 7,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    backgroundColor: PALETTE.surface,
  },
  tabText: { fontFamily: FONT.sansMedium, fontSize: 10.5, color: PALETTE.textMuted },
  readout: { flexDirection: 'row', alignItems: 'baseline', gap: 5 },
  readoutValue: { fontFamily: FONT.monoSemiBold, fontSize: 20, color: PALETTE.text },
  readoutUnit: { fontFamily: FONT.mono, fontSize: 11, color: PALETTE.textMuted },
  readoutMeta: { flex: 1, textAlign: 'right', fontFamily: FONT.mono, fontSize: 9.5, color: PALETTE.textFaint },
  chart: { height: CHART_HEIGHT, justifyContent: 'flex-end' },
  avgLine: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: 1,
    backgroundColor: 'rgba(163,180,194,0.28)',
  },
  bars: { flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: CHART_HEIGHT },
  bar: { flex: 1, borderRadius: 2, minHeight: 4 },
  empty: {
    flex: 1,
    fontFamily: FONT.sans,
    fontSize: 12,
    color: PALETTE.textFaint,
    textAlign: 'center',
    alignSelf: 'center',
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: PALETTE.outlineSoft,
    paddingTop: 8,
  },
  footItem: { fontFamily: FONT.mono, fontSize: 9.5, color: PALETTE.textMuted },
});
