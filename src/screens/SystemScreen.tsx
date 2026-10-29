import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { ActivityIndicator, Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useIsFocused } from '@react-navigation/native';
import AppHeader from '../components/AppHeader';
import { Divider, Panel, Row, SectionHeader } from '../components/Panel';
import WorkersScreen from './WorkersScreen';
import CalibrationScreen from './CalibrationScreen';
import { API_BASE, api, DEFAULT_DEVICE_ID } from '../api';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';

type Section = 'overview' | 'badges' | 'calibration';

function HealthRow({
  icon,
  label,
  value,
  ok,
  unknown,
}: {
  icon: keyof typeof MaterialCommunityIcons.glyphMap;
  label: string;
  value: string;
  ok: boolean;
  unknown?: boolean;
}) {
  const color = unknown ? PALETTE.textFaint : ok ? PALETTE.success : PALETTE.warning;
  return (
    <View style={styles.healthRow}>
      <MaterialCommunityIcons name={icon} size={16} color={PALETTE.textMuted} />
      <Text style={styles.healthLabel}>{label}</Text>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={[styles.healthValue, { color }]} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

export default function SystemScreen() {
  const focused = useIsFocused();
  const [section, setSection] = useState<Section>('overview');
  const [health, setHealth] = useState<any>(null);
  const [devices, setDevices] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [h, d] = await Promise.all([
        api.health(),
        api.devices().catch(() => ({ devices: [] })),
      ]);
      setHealth(h);
      setDevices(Array.isArray(d?.devices) ? d.devices : []);
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'Gateway unreachable');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (!focused || section !== 'overview') return;
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [focused, section, load]);

  const onRefresh = () => {
    setRefreshing(true);
    load();
  };

  return (
    <View style={styles.root}>
      <AppHeader
        title="System"
        subtitle="Gateway · diagnostics"
        connected={!error}
        rightIcon="refresh"
        rightLabel="Refresh gateway health"
        onRightPress={load}
      />

      <View style={styles.tabs}>
        {(
          [
            ['overview', 'Overview', 'view-dashboard-outline'],
            ['badges', 'Badges', 'badge-account-outline'],
            ['calibration', 'Calibration', 'tune-variant'],
          ] as [Section, string, keyof typeof MaterialCommunityIcons.glyphMap][]
        ).map(([key, label, icon]) => {
          const active = section === key;
          return (
            <Pressable
              key={key}
              onPress={() => setSection(key)}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              style={[styles.tab, active && styles.tabActive]}
            >
              <MaterialCommunityIcons
                name={icon}
                size={15}
                color={active ? PALETTE.onPrimaryContainer : PALETTE.textMuted}
              />
              <Text style={[styles.tabText, active && styles.tabTextActive]}>{label}</Text>
            </Pressable>
          );
        })}
      </View>

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
        {section === 'overview' && (
          <>
            {!!error && (
              <View style={styles.banner}>
                <MaterialCommunityIcons name="lan-disconnect" size={15} color={PALETTE.warning} />
                <Text style={styles.bannerText}>{error}</Text>
              </View>
            )}

            {loading && !health && (
              <ActivityIndicator color={PALETTE.primary} style={{ marginTop: SPACING['2xl'] }} />
            )}

            <SectionHeader title="GATEWAY HEALTH" icon="server-network" />
            <Panel style={{ paddingVertical: SPACING.sm }}>
              <HealthRow
                icon="lan-connect"
                label="MQTT broker"
                value={health ? (health.mqtt_connected ? 'CONNECTED' : 'OFFLINE') : '--'}
                ok={!!health?.mqtt_connected}
              />
              <Divider />
              <HealthRow
                icon="video-outline"
                label="Camera"
                value={health ? (health.camera_available ? 'AVAILABLE' : 'NOT FOUND') : '--'}
                ok={!!health?.camera_available}
              />
              <Divider />
              <HealthRow
                icon="robot-outline"
                label="Roboflow model"
                value={health ? (health.roboflow_configured ? 'CONFIGURED' : 'LOCAL FALLBACK') : '--'}
                ok={!!health?.roboflow_configured}
                unknown={!health}
              />
              <Divider />
              <HealthRow
                icon="send-outline"
                label="Telegram alerts"
                value={health ? (health.telegram_configured ? 'CONFIGURED' : 'NOT SET') : '--'}
                ok={!!health?.telegram_configured}
                unknown={!health}
              />
            </Panel>

            <SectionHeader title="CONNECTION" icon="link-variant" style={{ marginTop: SPACING.xl }} />
            <Panel style={{ paddingVertical: SPACING.sm }}>
              <Row label="API base" value={API_BASE.replace(/^https?:\/\//, '')} mono />
              <Divider />
              <Row label="Device" value={DEFAULT_DEVICE_ID} mono />
              <Divider />
              <Row label="Devices seen" value={devices.length ? devices.join(', ') : '--'} mono />
              <Divider />
              <Row label="Broker" value={health?.mqtt_broker || '--'} mono />
              <Divider />
              <Row label="App build" value="1.0.0 · armor-app" mono />
            </Panel>

            <SectionHeader title="REDUNDANCY" icon="swap-horizontal" style={{ marginTop: SPACING.xl }} />
            <Panel>
              <View style={styles.noteRow}>
                <MaterialCommunityIcons name="check-circle-outline" size={16} color={PALETTE.success} />
                <Text style={styles.noteText}>
                  Blynk V0 (motor) and V5 (bench) remain wired in firmware as a second control path. The
                  app talks MQTT through this gateway, and firmware mirrors state back to Blynk.
                </Text>
              </View>
              <View style={styles.noteDivider} />
              <View style={styles.noteRow}>
                <MaterialCommunityIcons name="shield-lock-outline" size={16} color={PALETTE.danger} />
                <Text style={styles.noteText}>
                  Interlocks are enforced in the actuation loop, not in either UI: motor runs only when
                  requested AND no lockout is active.
                </Text>
              </View>
            </Panel>

            <Text style={styles.footnote}>
              Gateway time {health?.timestamp ? health.timestamp.replace('T', ' ').slice(0, 19) : '--'} UTC
            </Text>
          </>
        )}

        {section === 'badges' && <WorkersScreen />}
        {section === 'calibration' && <CalibrationScreen />}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: PALETTE.bg },
  tabs: {
    flexDirection: 'row',
    gap: 6,
    paddingHorizontal: SPACING.lg,
    paddingTop: SPACING.md,
    paddingBottom: SPACING.sm,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    paddingVertical: 8,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    backgroundColor: PALETTE.surface,
  },
  tabActive: { backgroundColor: PALETTE.primaryContainer, borderColor: 'rgba(111,183,255,0.45)' },
  tabText: { fontFamily: FONT.sansMedium, fontSize: 11.5, color: PALETTE.textMuted },
  tabTextActive: { color: PALETTE.onPrimaryContainer },
  content: { paddingHorizontal: SPACING.lg, paddingTop: SPACING.sm, paddingBottom: SPACING['2xl'] * 2 },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    backgroundColor: 'rgba(227,179,65,0.10)',
    borderWidth: 1,
    borderColor: 'rgba(227,179,65,0.32)',
    borderRadius: RADIUS.md,
    paddingHorizontal: SPACING.md,
    paddingVertical: 9,
    marginBottom: SPACING.md,
  },
  bannerText: { flex: 1, fontFamily: FONT.sans, fontSize: 12, color: PALETTE.onWarningContainer },
  healthRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10 },
  healthLabel: { flex: 1, fontFamily: FONT.sans, fontSize: 13, color: PALETTE.textMuted },
  dot: { width: 6, height: 6, borderRadius: 3 },
  healthValue: { fontFamily: FONT.monoMedium, fontSize: 10.5, letterSpacing: 0.4 },
  noteRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  noteText: { flex: 1, fontFamily: FONT.sans, fontSize: 12, lineHeight: 18, color: PALETTE.textMuted },
  noteDivider: { height: 1, backgroundColor: PALETTE.outlineSoft, marginVertical: SPACING.md },
  footnote: {
    fontFamily: FONT.mono,
    fontSize: 10,
    color: PALETTE.textFaint,
    marginTop: SPACING.lg,
    textAlign: 'center',
  },
});
