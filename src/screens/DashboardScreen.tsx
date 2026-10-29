import React, { useMemo } from 'react';
import { RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { ActivityIndicator, Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useIsFocused, useNavigation } from '@react-navigation/native';
import AppHeader from '../components/AppHeader';
import StatusPill from '../components/StatusPill';
import MotorControl from '../components/MotorControl';
import MetricCard from '../components/MetricCard';
import Attribution from '../components/Attribution';
import TrendChart from '../components/TrendChart';
import { Divider, Panel, SectionHeader } from '../components/Panel';
import { useMachineStatus } from '../hooks/useMachineStatus';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';
import { ago, clock, num } from '../utils/format';

export default function DashboardScreen() {
  const focused = useIsFocused();
  const navigation = useNavigation<any>();
  const { status, telemetry, decomposition, error, loading, refresh } = useMachineStatus(
    2000,
    40,
    focused,
  );
  const [refreshing, setRefreshing] = React.useState(false);

  const onRefresh = React.useCallback(async () => {
    setRefreshing(true);
    await refresh();
    setRefreshing(false);
  }, [refresh]);

  const history = useMemo(() => {
    const pick = (key: string) =>
      telemetry
        .map((s) => Number(s?.[key]))
        .filter((n) => Number.isFinite(n));
    return {
      rms: pick('rms'),
      voltage: pick('voltage_v'),
      current: pick('current_ma'),
      temp: pick('temperature_c'),
    };
  }, [telemetry]);

  const anomaly = status?.is_anomaly === true;
  const locked = !!status?.interlock_active;
  const breach = !!status?.proximity_breach_active;
  const motorRunning = status?.motor_state === 'RUNNING';
  const vicinityActive = !!status?.vicinity_presence_active;
  const authorized =
    String(status?.vicinity_status || '').toUpperCase() === 'AUTHORIZED_OPERATOR_PPE_VERIFIED';

  const recent = telemetry.slice(-3).reverse();

  if (loading && !status) {
    return (
      <View style={styles.root}>
        <AppHeader title="ARMOR" subtitle="CELL 01 · MACHINE NODE" connected={false} />
        <View style={styles.loading}>
          <ActivityIndicator color={PALETTE.primary} />
          <Text style={styles.loadingText}>Contacting machine node…</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      <AppHeader
        title="ARMOR"
        subtitle="CELL 01 · MACHINE NODE"
        connected={!error}
        rightIcon="cog-outline"
        rightLabel="Open system"
        onRightPress={() => navigation.navigate('System')}
      />

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={PALETTE.primary}
            colors={[PALETTE.primary]}
            progressBackgroundColor={PALETTE.surfaceContainer}
          />
        }
      >
        {!!error && (
          <View style={styles.banner}>
            <MaterialCommunityIcons name="lan-disconnect" size={16} color={PALETTE.warning} />
            <Text style={styles.bannerText} numberOfLines={2}>
              {error}
            </Text>
          </View>
        )}

        <View style={styles.rail}>
          <StatusPill
            label="MOTOR"
            value={locked ? 'LOCKED' : motorRunning ? 'RUNNING' : 'IDLE'}
            icon={locked ? 'lock' : motorRunning ? 'engine' : 'engine-off-outline'}
            tone={locked ? 'danger' : motorRunning ? 'ok' : 'info'}
          />
          <StatusPill
            label="INTERLOCK"
            value={locked ? 'ACTIVE' : 'CLEAR'}
            icon={locked ? 'shield-lock' : 'shield-check-outline'}
            tone={locked ? 'danger' : 'ok'}
          />
          <StatusPill
            label="PROXIMITY"
            value={breach ? 'BREACH' : 'CLEAR'}
            icon={breach ? 'radar' : 'access-point-check'}
            tone={breach ? 'warn' : 'ok'}
          />
        </View>

        <View style={[styles.hero, anomaly && styles.heroBad]}>
          <View pointerEvents="none" style={StyleSheet.absoluteFill}>
            {[0.18, 0.42, 0.68, 0.9].map((p) => (
              <View key={`h${p}`} style={[styles.gridLineH, { top: `${p * 100}%` }]} />
            ))}
            {[0.2, 0.5, 0.8].map((p) => (
              <View key={`v${p}`} style={[styles.gridLineV, { left: `${p * 100}%` }]} />
            ))}
          </View>

          <View style={styles.heroTop}>
            <Text style={styles.heroLabel}>ANOMALY STATUS</Text>
            <View style={styles.heroReadout}>
              <Text style={styles.heroReadoutValue}>{num(status?.current_rms, 3)}</Text>
              <Text style={styles.heroReadoutUnit}>g RMS</Text>
            </View>
          </View>

          <Text style={[styles.heroValue, anomaly && { color: PALETTE.danger }]}>
            {anomaly ? 'ANOMALY' : 'NOMINAL'}
          </Text>

          <View
            style={[
              styles.capsule,
              anomaly
                ? { backgroundColor: 'rgba(255,107,107,0.12)', borderColor: 'rgba(255,107,107,0.36)' }
                : { backgroundColor: 'rgba(69,212,138,0.10)', borderColor: 'rgba(69,212,138,0.32)' },
            ]}
          >
            <MaterialCommunityIcons
              name={anomaly ? 'alert-outline' : 'check-decagram-outline'}
              size={13}
              color={anomaly ? PALETTE.danger : PALETTE.success}
            />
            <Text style={[styles.capsuleText, { color: anomaly ? PALETTE.danger : PALETTE.success }]}>
              {anomaly ? 'ISOLATION FOREST · FLAGGED' : 'ISOLATION FOREST · HEALTHY'}
            </Text>
          </View>

          <Text style={styles.heroMeta}>
            {anomaly && status?.top_contributor && status.top_contributor !== 'none'
              ? `Top contributor: ${String(status.top_contributor).replace(/_/g, ' ')}`
              : status?.vicinity_presence_active
                ? `Vicinity ${status?.vicinity_status || 'PRESENT'} · worker ${status?.active_worker_id || 'unassigned'}`
                : 'No worker in the cell · machine isolated'}
          </Text>

          {!!status?.predictive_advisory && (
            <View style={styles.advisory}>
              <MaterialCommunityIcons name="robot-outline" size={14} color={PALETTE.info} />
              <Text style={styles.advisoryText} numberOfLines={3}>
                {status.predictive_advisory}
              </Text>
            </View>
          )}
        </View>

        <MotorControl status={status} onChanged={refresh} />

        {vicinityActive && (
          <View style={[styles.vicinity, authorized && styles.vicinityOk]}>
            <MaterialCommunityIcons
              name={authorized ? 'shield-account' : 'shield-alert-outline'}
              size={16}
              color={authorized ? PALETTE.success : PALETTE.warning}
            />
            <View style={styles.vicinityText}>
              <Text style={[styles.vicinityTitle, { color: authorized ? PALETTE.success : PALETTE.warning }]}>
                {authorized ? 'PPE verified — operation authorized' : 'Worker in vicinity — verifying PPE'}
              </Text>
              <Text style={styles.vicinityBody}>
                {authorized
                  ? `${status?.active_worker_id || 'Worker'} detected inside the 1.5 m vicinity with a verified helmet. No breach.`
                  : `${status?.active_worker_id || 'Worker'} inside the 1.5 m vicinity. Vision gate is checking helmet compliance.`}
              </Text>
            </View>
          </View>
        )}

        <SectionHeader
          title="LIVE READINGS"
          icon="waveform"
          right={<Text style={styles.updated}>Updated {ago(status?.last_telemetry_at)}</Text>}
          style={{ marginTop: SPACING.xl }}
        />

        <View style={styles.grid}>
          <View style={styles.gridRow}>
            <MetricCard
              label="VIBRATION"
              value={num(status?.current_rms, 3)}
              unit="g"
              icon="waveform"
              history={history.rms}
              footerLeft="RMS"
              footerRight={anomaly ? 'outlier' : 'in band'}
              footerRightColor={anomaly ? PALETTE.warning : PALETTE.textFaint}
            />
            <MetricCard
              label="BUS VOLTAGE"
              value={num(status?.current_voltage_v, 2)}
              unit="V"
              icon="flash-outline"
              history={history.voltage}
              footerLeft="INA219"
              footerRight="12 V rail"
            />
          </View>
          <View style={styles.gridRow}>
            <MetricCard
              label="CURRENT DRAW"
              value={num(status?.current_ma, 1)}
              unit="mA"
              icon="current-dc"
              history={history.current}
              accent={PALETTE.info}
              footerLeft="INA219"
              footerRight={motorRunning ? 'loaded' : 'no load'}
            />
            <MetricCard
              label="TEMPERATURE"
              value={num(status?.current_temp_c, 1)}
              unit="°C"
              icon="thermometer"
              history={history.temp}
              accent={PALETTE.warning}
              footerLeft="DS18B20"
              footerRight={Number(status?.current_temp_c) > 45 ? 'hot' : 'normal'}
              footerRightColor={Number(status?.current_temp_c) > 45 ? PALETTE.warning : undefined}
            />
          </View>
        </View>

        <SectionHeader
          title="SENSOR ATTRIBUTION"
          icon="chart-donut"
          right={<Text style={styles.updated}>multi-modal · 5 s window</Text>}
          style={{ marginTop: SPACING.xl }}
        />
        <Attribution data={decomposition} />

        <SectionHeader
          title="TRENDS"
          icon="chart-areaspline"
          right={<Text style={styles.updated}>rolling · {telemetry.length} samples</Text>}
          style={{ marginTop: SPACING.xl }}
        />
        <TrendChart samples={telemetry} />

        <SectionHeader
          title="RECENT SAMPLES"
          icon="chart-timeline-variant"
          right={<Text style={styles.updated}>last {recent.length} of 40</Text>}
          style={{ marginTop: SPACING.xl }}
        />

        <Panel style={{ paddingVertical: SPACING.sm }}>
          {recent.length === 0 ? (
            <Text style={styles.empty}>No telemetry has arrived from this device yet.</Text>
          ) : (
            recent.map((s, i) => (
              <View key={`${s.ts}-${i}`}>
                {i > 0 && <Divider />}
                <View style={styles.sample}>
                  <Text style={styles.sampleTime}>{clock(s.ts)}</Text>
                  <Text style={styles.sampleValue}>{num(s.rms, 3)} g</Text>
                  <Text style={styles.sampleValue}>{num(s.temperature_c, 1)} °C</Text>
                  <Text style={styles.sampleValue}>{num(s.voltage_v, 2)} V</Text>
                </View>
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
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: SPACING.md },
  loadingText: { fontFamily: FONT.sans, fontSize: 13, color: PALETTE.textMuted },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.sm,
    backgroundColor: 'rgba(227,179,65,0.10)',
    borderWidth: 1,
    borderColor: 'rgba(227,179,65,0.32)',
    borderRadius: RADIUS.md,
    paddingHorizontal: SPACING.md,
    paddingVertical: 9,
    marginBottom: SPACING.md,
  },
  bannerText: { flex: 1, fontFamily: FONT.sans, fontSize: 12, color: PALETTE.onWarningContainer },
  rail: { flexDirection: 'row', gap: SPACING.sm, marginBottom: SPACING.md },
  hero: {
    backgroundColor: PALETTE.surfaceContainer,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    borderRadius: RADIUS.lg,
    padding: SPACING.lg,
    overflow: 'hidden',
    marginBottom: SPACING.lg,
  },
  heroBad: { borderColor: 'rgba(255,107,107,0.34)', backgroundColor: '#251A1D' },
  gridLineH: { position: 'absolute', left: 0, right: 0, height: 1, backgroundColor: 'rgba(111,183,255,0.06)' },
  gridLineV: { position: 'absolute', top: 0, bottom: 0, width: 1, backgroundColor: 'rgba(111,183,255,0.06)' },
  heroTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  heroLabel: {
    fontFamily: FONT.sansMedium,
    fontSize: 10.5,
    letterSpacing: 1.4,
    color: PALETTE.textMuted,
  },
  heroReadout: { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
  heroReadoutValue: {
    fontFamily: FONT.monoSemiBold,
    fontSize: 15,
    color: PALETTE.text,
  },
  heroReadoutUnit: { fontFamily: FONT.mono, fontSize: 10, color: PALETTE.textFaint },
  heroValue: {
    fontFamily: FONT.sansBold,
    fontSize: 34,
    lineHeight: 42,
    letterSpacing: -0.8,
    color: PALETTE.text,
    marginTop: 6,
  },
  capsule: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: 1,
    borderRadius: RADIUS.pill,
    paddingHorizontal: 10,
    paddingVertical: 4,
    marginTop: SPACING.sm,
  },
  capsuleText: { fontFamily: FONT.sansMedium, fontSize: 10, letterSpacing: 0.7 },
  heroMeta: {
    fontFamily: FONT.sans,
    fontSize: 12,
    lineHeight: 17,
    color: PALETTE.textMuted,
    marginTop: SPACING.md,
  },
  advisory: {
    flexDirection: 'row',
    gap: 7,
    alignItems: 'flex-start',
    marginTop: SPACING.md,
    paddingTop: SPACING.md,
    borderTopWidth: 1,
    borderTopColor: PALETTE.outlineSoft,
  },
  advisoryText: { flex: 1, fontFamily: FONT.sans, fontSize: 12, lineHeight: 17, color: PALETTE.info },
  updated: { fontFamily: FONT.mono, fontSize: 10.5, color: PALETTE.textFaint },
  vicinity: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 9,
    marginTop: SPACING.md,
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.md,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: 'rgba(227,179,65,0.32)',
    backgroundColor: 'rgba(227,179,65,0.08)',
  },
  vicinityOk: {
    borderColor: 'rgba(69,212,138,0.30)',
    backgroundColor: 'rgba(69,212,138,0.07)',
  },
  vicinityText: { flex: 1, gap: 3 },
  vicinityTitle: { fontFamily: FONT.sansSemiBold, fontSize: 12.5 },
  vicinityBody: { fontFamily: FONT.sans, fontSize: 11.5, lineHeight: 16, color: PALETTE.textMuted },
  grid: { gap: SPACING.sm },
  gridRow: { flexDirection: 'row', gap: SPACING.sm },
  empty: {
    fontFamily: FONT.sans,
    fontSize: 13,
    color: PALETTE.textMuted,
    padding: SPACING.md,
    textAlign: 'center',
  },
  sample: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: SPACING.xs,
    paddingVertical: 9,
    gap: 8,
  },
  sampleTime: { fontFamily: FONT.mono, fontSize: 11, color: PALETTE.textFaint, width: 66 },
  sampleValue: { fontFamily: FONT.mono, fontSize: 11.5, color: PALETTE.textMuted },
});
