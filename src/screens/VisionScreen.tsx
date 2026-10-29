import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useIsFocused } from '@react-navigation/native';
import AppHeader from '../components/AppHeader';
import CameraFeed, { VisionStatus } from '../components/CameraFeed';
import Snapshot from '../components/Snapshot';
import ActionButton from '../components/ActionButton';
import { Divider, Panel, Row, SectionHeader } from '../components/Panel';
import { api, DEFAULT_DEVICE_ID } from '../api';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';
import { pct, stamp } from '../utils/format';

type Inspection = {
  status?: 'idle' | 'processing' | 'complete';
  result?: any | null;
  vision_state?: string;
  is_frozen?: boolean;
  person_present?: boolean;
};

export default function VisionScreen() {
  const focused = useIsFocused();
  const [camera, setCamera] = useState<VisionStatus | null>(null);
  const [workerId, setWorkerId] = useState('WORKER_EMP_402');
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [starting, setStarting] = useState(false);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSnapshot, setShowSnapshot] = useState(true);
  const timer = useRef<any>(null);

  const loadInspection = useCallback(async () => {
    try {
      const res: Inspection = await api.visionInspectStatus();
      setInspection(res);
      return res;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    if (!focused) return;
    loadInspection();
    const id = setInterval(loadInspection, 4000);
    return () => clearInterval(id);
  }, [focused, loadInspection]);

  useEffect(() => () => clearInterval(timer.current), []);

  const runInspection = async () => {
    setStarting(true);
    setError(null);
    setShowSnapshot(true);
    try {
      await api.visionInspectStart(workerId.trim() || 'WORKER_EMP_402', DEFAULT_DEVICE_ID);
      setPolling(true);
      const startedAt = Date.now();
      clearInterval(timer.current);
      timer.current = setInterval(async () => {
        const res = await loadInspection();
        const done =
          res?.status === 'complete' ||
          res?.status === 'idle' ||
          Date.now() - startedAt > 30000;
        if (done) {
          clearInterval(timer.current);
          setPolling(false);
        }
      }, 1500);
    } catch (e: any) {
      setError(e?.message || 'Could not start inspection');
      setPolling(false);
    } finally {
      setStarting(false);
    }
  };

  const result = inspection?.result || null;
  const compliant = result?.compliant;
  const hasVerdict = compliant === true || compliant === false;
  const threshold = Number(result?.threshold_used ?? 0.65);
  const ratio = Number(result?.compliance_ratio ?? 0);
  const ratioPct = Math.max(0, Math.min(1, ratio));

  const cameraOk = camera?.camera_available === true;
  const modelOk = camera?.roboflow_configured === true;

  return (
    <View style={styles.root}>
      <AppHeader
        title="Vision"
        subtitle="Live camera · CELL 01"
        rightIcon="refresh"
        rightLabel="Refresh camera status"
      />

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={false}
            onRefresh={() => {
              loadInspection();
            }}
            tintColor={PALETTE.primary}
            colors={[PALETTE.primary]}
            progressBackgroundColor={PALETTE.surfaceContainer}
          />
        }
      >
        <CameraFeed onStatus={setCamera} />

        <SectionHeader title="HELMET CHECK" icon="hard-hat" style={{ marginTop: SPACING.xl }} />

        <Panel>
          <View style={styles.workerRow}>
            <View style={styles.workerLabel}>
              <MaterialCommunityIcons name="badge-account-outline" size={15} color={PALETTE.textMuted} />
              <Text style={styles.workerCaption}>WORKER</Text>
            </View>
            <TextInput
              value={workerId}
              onChangeText={setWorkerId}
              autoCapitalize="characters"
              autoCorrect={false}
              style={styles.input}
              placeholder="WORKER_EMP_402"
              placeholderTextColor={PALETTE.textFaint}
              selectionColor={PALETTE.primary}
              accessibilityLabel="Worker ID"
            />
          </View>

          <View style={styles.verdict}>
            {hasVerdict ? (
              <>
                <View
                  style={[
                    styles.verdictBadge,
                    compliant
                      ? { backgroundColor: 'rgba(69,212,138,0.10)', borderColor: 'rgba(69,212,138,0.34)' }
                      : { backgroundColor: 'rgba(255,107,107,0.10)', borderColor: 'rgba(255,107,107,0.36)' },
                  ]}
                >
                  <MaterialCommunityIcons
                    name={compliant ? 'shield-check' : 'shield-alert'}
                    size={18}
                    color={compliant ? PALETTE.success : PALETTE.danger}
                  />
                  <Text
                    style={[
                      styles.verdictLabel,
                      { color: compliant ? PALETTE.success : PALETTE.danger },
                    ]}
                  >
                    {compliant ? 'HELMET PASS' : 'HELMET FAIL'}
                  </Text>
                </View>

                <View style={styles.meter}>
                  <View style={styles.meterTrack}>
                    <View
                      style={[
                        styles.meterFill,
                        {
                          width: `${ratioPct * 100}%`,
                          backgroundColor: compliant ? PALETTE.success : PALETTE.danger,
                        },
                      ]}
                    />
                    <View style={[styles.meterThreshold, { left: `${threshold * 100}%` }]} />
                  </View>
                  <View style={styles.meterLabels}>
                    <Text style={styles.meterText}>Compliance {pct(ratio)}</Text>
                    <Text style={styles.meterText}>Threshold {pct(threshold)}</Text>
                  </View>
                </View>
              </>
            ) : (
              <View style={styles.verdictEmpty}>
                <MaterialCommunityIcons
                  name={polling ? 'progress-clock' : 'hard-hat'}
                  size={22}
                  color={PALETTE.textFaint}
                />
                <Text style={styles.verdictEmptyText}>
                  {polling
                    ? 'Analysing the frozen frame…'
                    : inspection?.person_present
                      ? 'Worker in frame — run an inspection.'
                      : 'No verdict yet. Place a worker in frame and run an inspection.'}
                </Text>
              </View>
            )}
          </View>

          {!!error && (
            <View style={styles.errorRow}>
              <MaterialCommunityIcons name="alert-circle-outline" size={14} color={PALETTE.warning} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          )}

          <ActionButton
            label={polling ? 'Inspecting…' : 'Run helmet inspection'}
            icon="camera-iris"
            loading={starting || polling}
            onPress={runInspection}
            style={{ marginTop: SPACING.md }}
          />

          <View style={styles.metaRow}>
            <View style={styles.metaItem}>
              <MaterialCommunityIcons name="clock-outline" size={12} color={PALETTE.textFaint} />
              <Text style={styles.metaText}>{result?.timestamp ? stamp(result.timestamp) : 'no run yet'}</Text>
            </View>
            <View style={styles.metaItem}>
              <MaterialCommunityIcons name="radar" size={12} color={PALETTE.textFaint} />
              <Text style={styles.metaText} numberOfLines={1}>
                {result?.detection_source
                  ? String(result.detection_source).replace(/_/g, ' ').toLowerCase()
                  : camera?.vision_state || 'engine idle'}
              </Text>
            </View>
          </View>

          {hasVerdict && !!result?.snapshot_path && (
            <>
              <Divider />
              <View style={styles.snapshotHead}>
                <Text style={styles.snapshotTitle}>Evidence snapshot</Text>
                <Text style={styles.snapshotLink} onPress={() => setShowSnapshot((v) => !v)}>
                  {showSnapshot ? 'Hide' : 'Show'}
                </Text>
              </View>
              {showSnapshot && (
                <Snapshot
                  path={result.snapshot_path}
                  caption={`${result.worker_id || workerId} · ${compliant ? 'PASS' : 'FAIL'} · ${pct(ratio)}`}
                />
              )}
            </>
          )}
        </Panel>

        <SectionHeader title="CAPTURE STATUS" icon="video-check-outline" style={{ marginTop: SPACING.xl }} />

        <Panel style={{ paddingVertical: SPACING.sm }}>
          <View style={styles.statusRow}>
            <MaterialCommunityIcons
              name={cameraOk ? 'check-circle' : 'close-circle'}
              size={16}
              color={cameraOk ? PALETTE.success : PALETTE.danger}
            />
            <Text style={styles.statusLabel}>Camera connected</Text>
            <Text style={styles.statusValue}>{cameraOk ? 'YES' : 'NO'}</Text>
          </View>
          <Divider />
          <View style={styles.statusRow}>
            <MaterialCommunityIcons
              name={modelOk ? 'check-circle' : 'alert-circle'}
              size={16}
              color={modelOk ? PALETTE.success : PALETTE.warning}
            />
            <Text style={styles.statusLabel}>Roboflow model</Text>
            <Text style={styles.statusValue}>{modelOk ? 'CONFIGURED' : 'LOCAL FALLBACK'}</Text>
          </View>
          <Divider />
          <View style={styles.statusRow}>
            <MaterialCommunityIcons
              name={polling ? 'progress-clock' : 'sleep'}
              size={16}
              color={polling ? PALETTE.primary : PALETTE.textFaint}
            />
            <Text style={styles.statusLabel}>Inspector</Text>
            <Text style={styles.statusValue}>{polling ? 'RUNNING' : 'IDLE'}</Text>
          </View>
          <Divider />
          <Row label="Camera source" value={camera?.camera_source || '--'} mono />
        </Panel>

        <Text style={styles.footnote}>
          Camera frames are polled as single JPEGs at ~2 fps. The feed is letterboxed, never cropped, so
          the full inspection frame stays visible.
        </Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: PALETTE.bg },
  content: { paddingHorizontal: SPACING.lg, paddingTop: SPACING.md, paddingBottom: SPACING['2xl'] * 2 },
  workerRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.md },
  workerLabel: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  workerCaption: { fontFamily: FONT.sansMedium, fontSize: 10, letterSpacing: 1.2, color: PALETTE.textMuted },
  input: {
    flex: 1,
    fontFamily: FONT.mono,
    fontSize: 13,
    color: PALETTE.text,
    backgroundColor: PALETTE.surfaceContainer,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    borderRadius: RADIUS.sm,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  verdict: { marginTop: SPACING.md },
  verdictBadge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    borderWidth: 1,
    borderRadius: RADIUS.md,
    paddingHorizontal: 11,
    paddingVertical: 7,
  },
  verdictLabel: { fontFamily: FONT.sansSemiBold, fontSize: 12.5, letterSpacing: 1 },
  meter: { marginTop: SPACING.md },
  meterTrack: {
    height: 8,
    borderRadius: 4,
    backgroundColor: PALETTE.surfaceHighest,
    overflow: 'hidden',
    justifyContent: 'center',
  },
  meterFill: { height: 8, borderRadius: 4 },
  meterThreshold: {
    position: 'absolute',
    top: -1,
    width: 2,
    height: 10,
    backgroundColor: PALETTE.text,
    opacity: 0.8,
  },
  meterLabels: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
  meterText: { fontFamily: FONT.mono, fontSize: 10, color: PALETTE.textMuted },
  verdictEmpty: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  verdictEmptyText: {
    flex: 1,
    fontFamily: FONT.sans,
    fontSize: 12.5,
    lineHeight: 18,
    color: PALETTE.textMuted,
  },
  errorRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 7, marginTop: SPACING.md },
  errorText: { flex: 1, fontFamily: FONT.sans, fontSize: 12, lineHeight: 17, color: PALETTE.warning },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: SPACING.md, gap: 8 },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 5, flexShrink: 1 },
  metaText: { fontFamily: FONT.mono, fontSize: 10, color: PALETTE.textFaint },
  snapshotHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginVertical: SPACING.md,
  },
  snapshotTitle: { fontFamily: FONT.sansMedium, fontSize: 12, color: PALETTE.text },
  snapshotLink: { fontFamily: FONT.sansMedium, fontSize: 12, color: PALETTE.primary },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    paddingVertical: 10,
  },
  statusLabel: { flex: 1, fontFamily: FONT.sans, fontSize: 13, color: PALETTE.textMuted },
  statusValue: { fontFamily: FONT.monoMedium, fontSize: 11, color: PALETTE.text },
  footnote: {
    fontFamily: FONT.sans,
    fontSize: 11,
    lineHeight: 16,
    color: PALETTE.textFaint,
    marginTop: SPACING.lg,
  },
});
