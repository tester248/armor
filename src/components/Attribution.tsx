import React, { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { Panel } from './Panel';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';
import { num } from '../utils/format';

/* ──────────────────────────────────────────────────────────────────────────
   Sensor attribution — mobile port of the dashboard decomposition HUD.
   The gateway scores each modality (vibration, current, voltage/power,
   temperature) against the calibrated running baseline and reports a weight
   share per modality. We render those shares as a ranked bar list so an
   operator can see WHICH sensor is driving the fault score.
   ────────────────────────────────────────────────────────────────────────── */

type Channel = {
  value?: number | null;
  nominal_mean?: number | null;
  nominal_std?: number | null;
  deviation_sigma?: number | null;
};

type Modality = {
  name?: string;
  weight_pct?: number | null;
  sub_score_pct?: number | null;
  status?: string | null;
  channels?: Record<string, Channel>;
};

export type Decomposition = {
  anomaly_score?: number | null;
  decision_threshold?: number | null;
  is_anomaly?: boolean;
  anomaly_percentage?: number | null;
  top_contributor?: string | null;
  modalities?: Record<string, Modality>;
};

const META: Record<
  string,
  { label: string; short: string; icon: keyof typeof MaterialCommunityIcons.glyphMap; color: string }
> = {
  vibration: { label: 'Vibration', short: 'ADXL345', icon: 'waveform', color: PALETTE.primary },
  current: { label: 'Motor current', short: 'INA219', icon: 'current-dc', color: PALETTE.info },
  voltage_power: {
    label: 'Voltage & power',
    short: 'INA219',
    icon: 'flash-outline',
    color: PALETTE.success,
  },
  temperature: {
    label: 'Temperature',
    short: 'DS18B20',
    icon: 'thermometer',
    color: PALETTE.warning,
  },
};

const UNITS: Record<string, { unit: string; digits: number; label: string }> = {
  rms_g: { unit: 'g', digits: 3, label: 'RMS' },
  crest_factor: { unit: '', digits: 2, label: 'Crest' },
  mean_current_ma: { unit: 'mA', digits: 1, label: 'Mean' },
  peak_current_ma: { unit: 'mA', digits: 1, label: 'Peak' },
  voltage_v: { unit: 'V', digits: 2, label: 'Bus' },
  power_mw: { unit: 'mW', digits: 0, label: 'Power' },
  temperature_c: { unit: '°C', digits: 1, label: 'Temp' },
};

function channelLine(channels?: Record<string, Channel>): string | null {
  if (!channels) return null;
  const entries = Object.entries(channels);
  if (entries.length === 0) return null;
  const [key, ch] = entries[0];
  const meta = UNITS[key] || { unit: '', digits: 2, label: key.replace(/_/g, ' ') };
  const value = num(ch?.value, meta.digits);
  const unit = meta.unit ? ` ${meta.unit}` : '';
  const sigma = Number(ch?.deviation_sigma);
  const dev = Number.isFinite(sigma) ? ` · ${sigma.toFixed(2)}σ` : '';
  return `${meta.label} ${value}${unit}${dev}`;
}

export default function Attribution({ data }: { data?: Decomposition | null }) {
  const rows = useMemo(() => {
    const mods = data?.modalities || {};
    return Object.entries(mods)
      .map(([key, m]) => ({
        key,
        meta: META[key] || {
          label: m?.name || key,
          short: '',
          icon: 'chip' as const,
          color: PALETTE.textMuted,
        },
        weight: Math.max(0, Math.min(100, Number(m?.weight_pct) || 0)),
        sub: Number(m?.sub_score_pct) || 0,
        status: String(m?.status || 'NOMINAL').toUpperCase(),
        channels: m?.channels,
      }))
      .sort((a, b) => b.weight - a.weight);
  }, [data]);

  const score = Math.max(0, Math.min(100, Number(data?.anomaly_percentage) || 0));
  const flagged = data?.is_anomaly === true;
  const peak = rows[0]?.weight ?? 0;
  const topLabel =
    rows[0] && peak > 0
      ? `${rows[0].meta.label} · ${peak.toFixed(0)}% of score`
      : 'No dominant sensor — reading inside the calibrated band';

  if (!data || rows.length === 0) {
    return (
      <Panel>
        <Text style={styles.hint}>
          Waiting for the gateway to score the first telemetry window against the running baseline.
        </Text>
      </Panel>
    );
  }

  return (
    <Panel style={{ gap: SPACING.md }}>
      <View>
        <View style={styles.track}>
          <View
            style={[
              styles.fill,
              {
                width: `${Math.max(2, score)}%`,
                backgroundColor: flagged ? PALETTE.danger : PALETTE.success,
              },
            ]}
          />
        </View>
        <View style={styles.trackMeta}>
          <Text style={styles.trackText}>fault score {score.toFixed(1)}%</Text>
          <View
            style={[
              styles.scoreChip,
              flagged
                ? { backgroundColor: 'rgba(255,107,107,0.10)', borderColor: 'rgba(255,107,107,0.36)' }
                : { backgroundColor: 'rgba(69,212,138,0.08)', borderColor: 'rgba(69,212,138,0.28)' },
            ]}
          >
            <Text style={[styles.scoreText, { color: flagged ? PALETTE.danger : PALETTE.success }]}>
              {flagged ? 'FLAGGED' : 'NOMINAL'}
            </Text>
          </View>
        </View>
        <Text style={[styles.trackText, { marginTop: 3 }]}>
          threshold {num(data?.decision_threshold, 3)} · raw score {num(data?.anomaly_score, 3)}
        </Text>
      </View>

      <Text style={styles.top}>{topLabel}</Text>

      <View style={styles.rows}>
        {rows.map((r) => {
          const faulted = r.status !== 'NOMINAL';
          const detail = channelLine(r.channels);
          return (
            <View key={r.key} style={styles.row}>
              <View style={styles.rowHead}>
                <MaterialCommunityIcons name={r.meta.icon} size={14} color={r.meta.color} />
                <Text style={styles.rowName} numberOfLines={1}>
                  {r.meta.label}
                </Text>
                {!!r.meta.short && <Text style={styles.rowShort}>{r.meta.short}</Text>}
                <Text style={styles.rowWeight}>{r.weight.toFixed(1)}%</Text>
              </View>
              <View style={styles.rowTrack}>
                <View
                  style={[
                    styles.rowFill,
                    {
                      width: `${Math.max(r.weight > 0 ? 2 : 0, r.weight)}%`,
                      backgroundColor: faulted ? PALETTE.danger : r.meta.color,
                    },
                  ]}
                />
              </View>
              <View style={styles.rowFoot}>
                <Text style={styles.rowDetail} numberOfLines={1}>
                  {detail || 'no channel data'}
                </Text>
                <Text
                  style={[
                    styles.rowStatus,
                    { color: faulted ? PALETTE.danger : PALETTE.textFaint },
                  ]}
                >
                  {r.status} · sub {r.sub.toFixed(1)}%
                </Text>
              </View>
            </View>
          );
        })}
      </View>
    </Panel>
  );
}

const styles = StyleSheet.create({
  scoreChip: {
    paddingHorizontal: 8,
    paddingVertical: 2.5,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
  },
  scoreText: { fontFamily: FONT.monoSemiBold, fontSize: 9.5, letterSpacing: 0.6 },
  track: { height: 7, borderRadius: 4, backgroundColor: PALETTE.surfaceHighest, overflow: 'hidden' },
  fill: { height: 7, borderRadius: 4 },
  trackMeta: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
  trackText: { fontFamily: FONT.mono, fontSize: 9.5, color: PALETTE.textFaint },
  top: { fontFamily: FONT.sans, fontSize: 12.5, lineHeight: 18, color: PALETTE.text },
  hint: { fontFamily: FONT.sans, fontSize: 12, lineHeight: 17, color: PALETTE.textMuted, marginTop: SPACING.sm },
  rows: { gap: SPACING.md },
  row: { gap: 5 },
  rowHead: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  rowName: { flex: 1, fontFamily: FONT.sansMedium, fontSize: 12.5, color: PALETTE.text },
  rowShort: { fontFamily: FONT.mono, fontSize: 9, color: PALETTE.textFaint },
  rowWeight: { fontFamily: FONT.monoMedium, fontSize: 11, color: PALETTE.text },
  rowTrack: {
    height: 4,
    borderRadius: 2,
    backgroundColor: PALETTE.surfaceHighest,
    overflow: 'hidden',
  },
  rowFill: { height: 4, borderRadius: 2 },
  rowFoot: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
  rowDetail: { flex: 1, fontFamily: FONT.mono, fontSize: 9.5, color: PALETTE.textFaint },
  rowStatus: { fontFamily: FONT.mono, fontSize: 9.5 },
});
