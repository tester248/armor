import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { api, DEFAULT_DEVICE_ID } from '../api';
import { Divider, Panel, Row } from '../components/Panel';
import ActionButton from '../components/ActionButton';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';
import { num } from '../utils/format';

const CONTAMINATION = [0.01, 0.03, 0.05, 0.1, 0.2];
const MIN_SAMPLES = 20;

/** IsolationForest calibration + anomaly audit. Rendered inside the System hub. */
export default function CalibrationScreen() {
  const [model, setModel] = useState<any>(null);
  const [anomalies, setAnomalies] = useState<any[]>([]);
  const [sampleCount, setSampleCount] = useState(0);
  const [contamination, setContamination] = useState(0.05);
  const [calibrating, setCalibrating] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, a, t] = await Promise.all([
        api.model(DEFAULT_DEVICE_ID).catch(() => null),
        api.anomalies(DEFAULT_DEVICE_ID, 8).catch(() => ({ anomalies: [] })),
        api.telemetry(DEFAULT_DEVICE_ID, 500).catch(() => ({ samples: [] })),
      ]);
      setModel(m?.model_package || null);
      setAnomalies(Array.isArray(a?.anomalies) ? a.anomalies : []);
      setSampleCount(Array.isArray(t?.samples) ? t.samples.length : 0);
    } catch (e: any) {
      setMsg(e?.message || 'Could not load model state');
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, [load]);

  const runCalibration = async () => {
    setCalibrating(true);
    setMsg(null);
    try {
      const res = await api.calibrate(DEFAULT_DEVICE_ID, contamination);
      setMsg(`Calibration complete · ${res.window_count ?? '--'} windows · quality ${num(res.quality, 3)}`);
      await load();
    } catch (e: any) {
      setMsg(e?.message || 'Calibration failed');
    } finally {
      setCalibrating(false);
    }
  };

  const pkg = (() => {
    const raw = model?.model_package ?? model;
    if (!raw) return {};
    if (typeof raw === 'string') {
      try {
        return JSON.parse(raw);
      } catch {
        return {};
      }
    }
    return raw;
  })();
  const baseline = model?.baseline_stats || {};
  const thresholds = pkg?.thresholds || {};
  const ready = sampleCount >= MIN_SAMPLES;
  const progress = Math.max(0.02, Math.min(1, sampleCount / MIN_SAMPLES));

  return (
    <View style={styles.wrap}>
      {!!msg && (
        <View style={styles.msg}>
          <MaterialCommunityIcons name="information-outline" size={14} color={PALETTE.info} />
          <Text style={styles.msgText}>{msg}</Text>
        </View>
      )}

      <Panel style={{ gap: SPACING.sm }}>
        <View style={styles.head}>
          <MaterialCommunityIcons name="brain" size={17} color={PALETTE.primary} />
          <Text style={styles.title}>Anomaly model</Text>
          <View
            style={[
              styles.badge,
              model
                ? { backgroundColor: 'rgba(69,212,138,0.10)', borderColor: 'rgba(69,212,138,0.30)' }
                : { backgroundColor: 'rgba(227,179,65,0.10)', borderColor: 'rgba(227,179,65,0.32)' },
            ]}
          >
            <Text style={[styles.badgeText, { color: model ? PALETTE.success : PALETTE.warning }]}>
              {model ? 'CALIBRATED' : 'NO MODEL'}
            </Text>
          </View>
        </View>

        {model ? (
          <>
            <Row label="Training windows" value={String(model.window_count ?? '--')} mono />
            <Divider />
            <Row label="Quality" value={num(model.quality, 3)} mono />
            <Divider />
            <Row label="Baseline mean acc" value={`${num(baseline.mean_acc, 4)} g`} mono />
            <Divider />
            <Row label="Baseline std acc" value={`${num(baseline.std_acc, 4)} g`} mono />
            <Divider />
            <Row label="Samples used" value={String(baseline.sample_count ?? '--')} mono />
            {thresholds.hysteresis_high !== undefined && (
              <>
                <Divider />
                <Row
                  label="Hysteresis high / low"
                  value={`${num(thresholds.hysteresis_high, 3)} / ${num(thresholds.hysteresis_low, 3)}`}
                  mono
                />
              </>
            )}
          </>
        ) : (
          <Text style={styles.hint}>
            Collect {MIN_SAMPLES}+ telemetry samples, then run calibration to build the IsolationForest
            baseline for this cell.
          </Text>
        )}
      </Panel>

      <Panel style={{ gap: SPACING.sm }}>
        <View style={styles.head}>
          <MaterialCommunityIcons name="database-outline" size={17} color={PALETTE.primary} />
          <Text style={styles.title}>Sample availability</Text>
          <Text style={styles.headMeta}>
            {sampleCount} / {MIN_SAMPLES}
          </Text>
        </View>
        <View style={styles.track}>
          <View
            style={[
              styles.fill,
              { width: `${progress * 100}%`, backgroundColor: ready ? PALETTE.success : PALETTE.warning },
            ]}
          />
        </View>
        <Text style={styles.hint}>
          {ready
            ? 'Enough samples to calibrate. Recalibrate after mechanical changes.'
            : `Need ${MIN_SAMPLES - sampleCount} more samples before calibration unlocks.`}
        </Text>
      </Panel>

      <Panel style={{ gap: SPACING.md }}>
        <View style={styles.head}>
          <MaterialCommunityIcons name="tune-variant" size={17} color={PALETTE.primary} />
          <Text style={styles.title}>Run calibration</Text>
        </View>

        <Text style={styles.label}>CONTAMINATION</Text>
        <View style={styles.chips}>
          {CONTAMINATION.map((v) => {
            const active = contamination === v;
            return (
              <Pressable
                key={v}
                onPress={() => setContamination(v)}
                style={[styles.chip, active && styles.chipActive]}
                accessibilityRole="radio"
                accessibilityState={{ selected: active }}
              >
                <Text style={[styles.chipText, active && styles.chipTextActive]}>{(v * 100).toFixed(0)}%</Text>
              </Pressable>
            );
          })}
        </View>

        <ActionButton
          label={calibrating ? 'Calibrating…' : 'Run calibration'}
          icon="play-circle-outline"
          loading={calibrating}
          disabled={!ready}
          onPress={runCalibration}
        />
      </Panel>

      <Panel style={{ paddingVertical: SPACING.sm }}>
        <View style={[styles.head, { paddingHorizontal: SPACING.xs, paddingVertical: SPACING.sm }]}>
          <MaterialCommunityIcons name="alert-circle-outline" size={16} color={PALETTE.warning} />
          <Text style={styles.title}>Recent anomaly scores</Text>
        </View>
        {anomalies.length === 0 ? (
          <Text style={styles.empty}>No anomaly records yet.</Text>
        ) : (
          anomalies.map((a, i) => (
            <View key={`${a.timestamp || i}-${i}`}>
              <Divider />
              <View style={styles.anomalyRow}>
                <Text style={styles.anomalyScore}>{num(a.anomaly_score, 3)}</Text>
                <Text style={styles.anomalyThreshold}>thr {num(a.threshold, 3)}</Text>
                <View
                  style={[
                    styles.badge,
                    a.is_anomaly
                      ? { backgroundColor: 'rgba(255,107,107,0.10)', borderColor: 'rgba(255,107,107,0.34)' }
                      : { backgroundColor: 'rgba(69,212,138,0.08)', borderColor: 'rgba(69,212,138,0.26)' },
                  ]}
                >
                  <Text
                    style={[styles.badgeText, { color: a.is_anomaly ? PALETTE.danger : PALETTE.success }]}
                  >
                    {a.is_anomaly ? 'ANOMALY' : 'NOMINAL'}
                  </Text>
                </View>
              </View>
            </View>
          ))
        )}
      </Panel>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: SPACING.md },
  msg: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingHorizontal: SPACING.md,
    paddingVertical: 8,
    borderRadius: RADIUS.md,
    backgroundColor: 'rgba(111,183,255,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(111,183,255,0.24)',
  },
  msgText: { flex: 1, fontFamily: FONT.sans, fontSize: 12, color: PALETTE.info },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { flex: 1, fontFamily: FONT.sansSemiBold, fontSize: 14.5, color: PALETTE.text },
  headMeta: { fontFamily: FONT.mono, fontSize: 11, color: PALETTE.textMuted },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.pill, borderWidth: 1 },
  badgeText: { fontFamily: FONT.sansSemiBold, fontSize: 9, letterSpacing: 0.8 },
  hint: { fontFamily: FONT.sans, fontSize: 12, lineHeight: 17, color: PALETTE.textMuted },
  label: { fontFamily: FONT.sansMedium, fontSize: 9.5, letterSpacing: 1.2, color: PALETTE.textFaint },
  track: { height: 6, borderRadius: 3, backgroundColor: PALETTE.surfaceHighest, overflow: 'hidden' },
  fill: { height: 6, borderRadius: 3 },
  chips: { flexDirection: 'row', gap: 6 },
  chip: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 7,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    backgroundColor: PALETTE.surfaceContainer,
  },
  chipActive: { backgroundColor: PALETTE.primaryContainer, borderColor: 'rgba(111,183,255,0.45)' },
  chipText: { fontFamily: FONT.mono, fontSize: 11.5, color: PALETTE.textMuted },
  chipTextActive: { color: PALETTE.onPrimaryContainer },
  empty: {
    fontFamily: FONT.sans,
    fontSize: 12,
    color: PALETTE.textMuted,
    textAlign: 'center',
    paddingVertical: SPACING.lg,
  },
  anomalyRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 9 },
  anomalyScore: { fontFamily: FONT.monoSemiBold, fontSize: 13, color: PALETTE.text, width: 58 },
  anomalyThreshold: { flex: 1, fontFamily: FONT.mono, fontSize: 10.5, color: PALETTE.textFaint },
});
