import React, { useCallback, useEffect, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { ActivityIndicator, Switch, Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useIsFocused } from '@react-navigation/native';
import AppHeader from '../components/AppHeader';
import MotorControl from '../components/MotorControl';
import ActionButton from '../components/ActionButton';
import { Divider, Panel, Row, SectionHeader } from '../components/Panel';
import { useMachineStatus } from '../hooks/useMachineStatus';
import { api, DEFAULT_DEVICE_ID } from '../api';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';
import { clock } from '../utils/format';

export default function InterlockScreen() {
  const focused = useIsFocused();
  const { status, error, refresh } = useMachineStatus(2000, 20, focused);

  const [busy, setBusy] = useState<null | 'LOCKOUT' | 'RESET' | 'BREACH' | 'BENCH'>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmLockout, setConfirmLockout] = useState(false);

  const [bench, setBench] = useState<boolean>(true);
  const [benchDirty, setBenchDirty] = useState(false);

  const [debugOpen, setDebugOpen] = useState(false);
  const [debug, setDebug] = useState<any[]>([]);

  const reportedBench = status?.bench_mode !== false;
  useEffect(() => {
    if (!benchDirty) setBench(reportedBench);
  }, [reportedBench, benchDirty]);

  const locked = !!status?.interlock_active;
  const breach = !!status?.proximity_breach_active;

  const run = useCallback(
    async (kind: 'LOCKOUT' | 'RESET' | 'BREACH', fn: () => Promise<any>) => {
      setBusy(kind);
      setActionError(null);
      try {
        await fn();
        await refresh();
      } catch (e: any) {
        setActionError(e?.message || 'Command failed');
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  const doLockout = () =>
    run('LOCKOUT', () => api.interlock('LOCKOUT', DEFAULT_DEVICE_ID)).then(() => setConfirmLockout(false));

  const doReset = () => run('RESET', () => api.interlock('RESET', DEFAULT_DEVICE_ID));

  const doBreach = () =>
    run('BREACH', () =>
      api.breach(DEFAULT_DEVICE_ID, status?.active_worker_id || 'WORKER_EMP_402', 'AA:BB:CC:DD:EE:FF'),
    );

  const toggleBench = async (next: boolean) => {
    setBench(next);
    setBenchDirty(true);
    setBusy('BENCH');
    setActionError(null);
    try {
      await api.benchMode(next, DEFAULT_DEVICE_ID);
      setBenchDirty(false);
    } catch (e: any) {
      setBench(reportedBench);
      setBenchDirty(false);
      setActionError(e?.message || 'Bench mode command failed');
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    if (!focused || !debugOpen) return;
    let alive = true;
    const load = async () => {
      try {
        const res = await api.debugMqtt(8);
        if (alive) setDebug(Array.isArray(res?.messages) ? res.messages : []);
      } catch {
        if (alive) setDebug([]);
      }
    };
    load();
    const id = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [focused, debugOpen]);

  return (
    <View style={styles.root}>
      <AppHeader
        title="Safety"
        subtitle="Cell 01 · interlock chain"
        connected={!error}
        rightIcon="history"
        rightLabel="Incident records"
      />

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={false}
            onRefresh={refresh}
            tintColor={PALETTE.primary}
            colors={[PALETTE.primary]}
            progressBackgroundColor={PALETTE.surfaceContainer}
          />
        }
      >
        <MotorControl status={status} onChanged={refresh} />

        <SectionHeader
          title="SAFETY INTERLOCK"
          icon="shield-lock-outline"
          style={{ marginTop: SPACING.xl }}
        />

        <Panel style={{ paddingVertical: SPACING.sm }}>
          <Row
            label="Interlock"
            value={locked ? 'ACTIVE — MOTOR CUT' : 'CLEAR'}
            valueColor={locked ? PALETTE.danger : PALETTE.success}
          />
          <Divider />
          <Row
            label="Proximity (ESP-NOW)"
            value={breach ? 'BREACH DETECTED' : 'CLEAR'}
            valueColor={breach ? PALETTE.warning : PALETTE.success}
          />
          <Divider />
          <Row label="Worker in cell" value={status?.active_worker_id || 'None'} mono />
          <Divider />
          <Row
            label="Vicinity"
            value={status?.vicinity_status || 'NOMINAL'}
            valueColor={
              String(status?.vicinity_status || '').toUpperCase() === 'NOMINAL'
                ? PALETTE.success
                : PALETTE.warning
            }
          />
        </Panel>

        {!!actionError && (
          <View style={styles.actionError}>
            <MaterialCommunityIcons name="alert-circle-outline" size={15} color={PALETTE.warning} />
            <Text style={styles.actionErrorText}>{actionError}</Text>
          </View>
        )}

        {confirmLockout ? (
          <View style={styles.confirm}>
            <Text style={styles.confirmTitle}>Issue emergency lockout?</Text>
            <Text style={styles.confirmBody}>
              This cuts motor power immediately and logs a LOCKOUT to the incident record. The motor
              cannot restart until the interlock is reset.
            </Text>
            <View style={styles.confirmActions}>
              <ActionButton
                label="Cancel"
                variant="outline"
                compact
                style={{ flex: 1 }}
                onPress={() => setConfirmLockout(false)}
              />
              <ActionButton
                label="Confirm lockout"
                variant="danger"
                icon="alert-octagon"
                compact
                style={{ flex: 1 }}
                loading={busy === 'LOCKOUT'}
                onPress={doLockout}
              />
            </View>
          </View>
        ) : (
          <ActionButton
            label="Emergency lockout"
            icon="alert-octagon"
            variant="danger"
            style={{ marginTop: SPACING.md }}
            onPress={() => setConfirmLockout(true)}
            accessibilityHint="Cuts motor power and requires an explicit reset"
          />
        )}

        <View style={styles.buttonRow}>
          <ActionButton
            label="Reset interlock"
            icon="lock-open-variant-outline"
            variant="outline"
            style={{ flex: 1 }}
            disabled={!locked}
            loading={busy === 'RESET'}
            onPress={doReset}
          />
          <ActionButton
            label="Simulate breach"
            icon="access-point"
            variant="tonal"
            style={{ flex: 1 }}
            loading={busy === 'BREACH'}
            onPress={doBreach}
          />
        </View>

        <SectionHeader
          title="BENCH TEST MODE"
          icon="bug-outline"
          style={{ marginTop: SPACING.xl }}
        />

        <Panel>
          <View style={styles.benchHead}>
            <View style={styles.benchText}>
              <Text style={styles.benchTitle}>
                {bench ? 'Bench mode on' : 'Live safety on'}
              </Text>
              <Text style={styles.benchBody}>
                Suppresses ESP-NOW proximity lockouts while calibrating. The machine node mirrors the
                switch over MQTT.
              </Text>
            </View>
            <Switch
              value={bench}
              onValueChange={toggleBench}
              disabled={busy === 'BENCH'}
              color={PALETTE.warning}
              accessibilityLabel="Bench test mode"
            />
          </View>
          {bench && (
            <View style={styles.benchWarn}>
              <MaterialCommunityIcons name="alert-outline" size={14} color={PALETTE.warning} />
              <Text style={styles.benchWarnText}>
                Proximity interlocks are suppressed. Do not leave the cell unattended.
              </Text>
            </View>
          )}
        </Panel>

        <SectionHeader
          title="MQTT DEBUG"
          icon="console"
          right={
            <Switch
              value={debugOpen}
              onValueChange={setDebugOpen}
              color={PALETTE.primary}
              accessibilityLabel="Show MQTT debug log"
            />
          }
          style={{ marginTop: SPACING.xl }}
        />

        <Panel style={{ padding: 0, overflow: 'hidden' }}>
          {!debugOpen ? (
            <Text style={styles.debugIdle}>
              Toggle to stream the last raw messages the gateway received.
            </Text>
          ) : debug.length === 0 ? (
            <View style={styles.debugEmpty}>
              <ActivityIndicator color={PALETTE.textFaint} size="small" />
              <Text style={styles.debugIdle}>Waiting for MQTT traffic…</Text>
            </View>
          ) : (
            debug.map((m, i) => (
              <View key={`${m.received_at}-${i}`} style={styles.debugRow}>
                <Text style={styles.debugTopic} numberOfLines={1}>
                  {String(m.topic || '').replace('machinocare/v1/', '~/')}
                </Text>
                <Text style={styles.debugPayload} numberOfLines={2}>
                  {JSON.stringify(m.payload)}
                </Text>
                <Text style={styles.debugTime}>{clock(m.received_at)}</Text>
              </View>
            ))
          )}
        </Panel>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: PALETTE.bg },
  content: { paddingHorizontal: SPACING.lg, paddingTop: SPACING.md, paddingBottom: SPACING['2xl'] * 2 },
  actionError: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    marginTop: SPACING.md,
    paddingHorizontal: SPACING.md,
    paddingVertical: 9,
    borderRadius: RADIUS.md,
    backgroundColor: 'rgba(227,179,65,0.10)',
    borderWidth: 1,
    borderColor: 'rgba(227,179,65,0.30)',
  },
  actionErrorText: { flex: 1, fontFamily: FONT.sans, fontSize: 12, color: PALETTE.onWarningContainer },
  confirm: {
    marginTop: SPACING.md,
    borderRadius: RADIUS.lg,
    borderWidth: 1,
    borderColor: 'rgba(255,107,107,0.42)',
    backgroundColor: '#251A1D',
    padding: SPACING.lg,
    gap: SPACING.sm,
  },
  confirmTitle: { fontFamily: FONT.sansSemiBold, fontSize: 15, color: PALETTE.danger },
  confirmBody: { fontFamily: FONT.sans, fontSize: 12.5, lineHeight: 18, color: PALETTE.textMuted },
  confirmActions: { flexDirection: 'row', gap: SPACING.sm, marginTop: SPACING.xs },
  buttonRow: { flexDirection: 'row', gap: SPACING.sm, marginTop: SPACING.md },
  benchHead: { flexDirection: 'row', alignItems: 'center', gap: SPACING.md },
  benchText: { flex: 1, gap: 4 },
  benchTitle: { fontFamily: FONT.sansSemiBold, fontSize: 15, color: PALETTE.text },
  benchBody: { fontFamily: FONT.sans, fontSize: 12, lineHeight: 17, color: PALETTE.textMuted },
  benchWarn: {
    flexDirection: 'row',
    gap: 7,
    alignItems: 'flex-start',
    marginTop: SPACING.md,
    paddingTop: SPACING.md,
    borderTopWidth: 1,
    borderTopColor: PALETTE.outlineSoft,
  },
  benchWarnText: { flex: 1, fontFamily: FONT.sans, fontSize: 12, lineHeight: 17, color: PALETTE.warning },
  debugIdle: {
    fontFamily: FONT.sans,
    fontSize: 12,
    color: PALETTE.textFaint,
    padding: SPACING.lg,
    textAlign: 'center',
  },
  debugEmpty: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 },
  debugRow: {
    paddingHorizontal: SPACING.md,
    paddingVertical: 9,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.outlineSoft,
    gap: 2,
  },
  debugTopic: { fontFamily: FONT.monoMedium, fontSize: 10.5, color: PALETTE.info },
  debugPayload: { fontFamily: FONT.mono, fontSize: 10, lineHeight: 14, color: PALETTE.textMuted },
  debugTime: { fontFamily: FONT.mono, fontSize: 9, color: PALETTE.textFaint },
});
