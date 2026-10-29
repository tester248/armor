import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { ActivityIndicator, Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useIsFocused } from '@react-navigation/native';
import AppHeader from '../components/AppHeader';
import Snapshot from '../components/Snapshot';
import ActionButton from '../components/ActionButton';
import { EmptyState, Panel } from '../components/Panel';
import { api, DEFAULT_DEVICE_ID } from '../api';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';
import { pct, stamp } from '../utils/format';

type Filter = 'open' | 'resolved' | 'all';

export default function IncidentsScreen() {
  const focused = useIsFocused();
  const [incidents, setIncidents] = useState<any[]>([]);
  const [filter, setFilter] = useState<Filter>('open');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openSnapshots, setOpenSnapshots] = useState<Record<string, boolean>>({});
  const [resetting, setResetting] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.incidents(DEFAULT_DEVICE_ID);
      setIncidents(Array.isArray(res?.incidents) ? res.incidents : []);
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'Could not load incidents');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!focused) return;
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, [focused, load]);

  const open = useMemo(() => incidents.filter((i) => !i.resolved), [incidents]);
  const resolved = useMemo(() => incidents.filter((i) => !!i.resolved), [incidents]);

  const shown = filter === 'open' ? open : filter === 'resolved' ? resolved : incidents;

  const authorizeReset = async (incident: any) => {
    setResetting(incident.incident_id);
    setError(null);
    try {
      await api.resetIncident(incident.incident_id, DEFAULT_DEVICE_ID, 'mobile_app');
      await load();
    } catch (e: any) {
      setError(e?.message || 'Reset failed');
    } finally {
      setResetting(null);
    }
  };

  return (
    <View style={styles.root}>
      <AppHeader
        title="Records"
        subtitle={`${incidents.length} incidents · ${open.length} open`}
        rightIcon="filter-variant"
        rightLabel="Cycle filter"
      />

      <View style={styles.filters}>
        {(
          [
            ['open', 'Open', open.length],
            ['resolved', 'Resolved', resolved.length],
            ['all', 'All', incidents.length],
          ] as [Filter, string, number][]
        ).map(([key, label, count]) => {
          const active = filter === key;
          return (
            <Pressable
              key={key}
              onPress={() => setFilter(key)}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              style={[styles.filter, active && styles.filterActive]}
            >
              <Text style={[styles.filterText, active && styles.filterTextActive]}>
                {label} {count > 0 ? count : ''}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={false}
            onRefresh={load}
            tintColor={PALETTE.primary}
            colors={[PALETTE.primary]}
            progressBackgroundColor={PALETTE.surfaceContainer}
          />
        }
      >
        {!!error && (
          <View style={styles.banner}>
            <MaterialCommunityIcons name="alert-circle-outline" size={15} color={PALETTE.warning} />
            <Text style={styles.bannerText}>{error}</Text>
          </View>
        )}

        {loading && incidents.length === 0 && (
          <ActivityIndicator color={PALETTE.primary} style={{ marginTop: SPACING['2xl'] }} />
        )}

        {!loading && shown.length === 0 && (
          <Panel style={{ marginTop: SPACING.md }}>
            <EmptyState
              icon={filter === 'open' ? 'shield-check-outline' : 'clipboard-text-clock-outline'}
              title={filter === 'open' ? 'No open violations' : 'Nothing recorded here yet'}
              body={
                filter === 'open'
                  ? 'Helmet failures and proximity breaches appear here the moment they are logged.'
                  : 'Resolved incidents are kept for audit. Switch to All to see the full log.'
              }
            />
          </Panel>
        )}

        {shown.map((inc) => {
          const isOpen = !inc.resolved;
          const snapVisible = openSnapshots[inc.incident_id] ?? isOpen;
          return (
            <View key={inc.incident_id} style={[styles.card, !isOpen && styles.cardResolved]}>
              <View style={styles.cardHead}>
                <View
                  style={[
                    styles.chip,
                    isOpen
                      ? { backgroundColor: 'rgba(255,107,107,0.10)', borderColor: 'rgba(255,107,107,0.36)' }
                      : { backgroundColor: 'rgba(69,212,138,0.10)', borderColor: 'rgba(69,212,138,0.30)' },
                  ]}
                >
                  <MaterialCommunityIcons
                    name={isOpen ? 'alert-outline' : 'check'}
                    size={13}
                    color={isOpen ? PALETTE.danger : PALETTE.success}
                  />
                  <Text
                    style={[styles.chipText, { color: isOpen ? PALETTE.danger : PALETTE.success }]}
                    numberOfLines={1}
                  >
                    {String(inc.violation_type || 'SAFETY EVENT').replace(/_/g, ' ')}
                  </Text>
                </View>
                <Text style={styles.time}>{stamp(inc.created_at)}</Text>
              </View>

              <View style={styles.identity}>
                <Text style={styles.worker}>{inc.worker_id || 'unknown worker'}</Text>
                <Text style={styles.mac} numberOfLines={1}>
                  {inc.badge_mac || 'no badge'} · {inc.device_id}
                </Text>
              </View>

              <View style={styles.stats}>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>COMPLIANCE</Text>
                  <Text
                    style={[
                      styles.statValue,
                      {
                        color: isOpen ? PALETTE.danger : PALETTE.success,
                      },
                    ]}
                  >
                    {pct(inc.compliance_ratio)}
                  </Text>
                </View>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>LOCKOUT</Text>
                  <Text style={styles.statValue}>{inc.interlock_issued ? 'ISSUED' : 'NONE'}</Text>
                </View>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>STATE</Text>
                  <Text style={[styles.statValue, { color: isOpen ? PALETTE.warning : PALETTE.success }]}>
                    {isOpen ? 'OPEN' : 'RESOLVED'}
                  </Text>
                </View>
              </View>

              {!!inc.snapshot_path && (
                <View style={styles.snapshotWrap}>
                  {snapVisible ? (
                    <Snapshot path={inc.snapshot_path} caption={inc.incident_id} />
                  ) : (
                    <Pressable
                      onPress={() =>
                        setOpenSnapshots((prev) => ({ ...prev, [inc.incident_id]: true }))
                      }
                      style={styles.snapshotPlaceholder}
                      accessibilityRole="button"
                      accessibilityLabel="Show evidence snapshot"
                    >
                      <MaterialCommunityIcons name="image-outline" size={18} color={PALETTE.textMuted} />
                      <Text style={styles.snapshotPlaceholderText}>Show evidence snapshot</Text>
                    </Pressable>
                  )}
                </View>
              )}

              <View style={styles.actions}>
                {isOpen ? (
                  <ActionButton
                    label="Authorize reset"
                    icon="lock-open-variant-outline"
                    variant="tonal"
                    compact
                    loading={resetting === inc.incident_id}
                    onPress={() => authorizeReset(inc)}
                    style={{ flex: 1 }}
                  />
                ) : (
                  <View style={styles.resolvedNote}>
                    <MaterialCommunityIcons name="account-check-outline" size={13} color={PALETTE.success} />
                    <Text style={styles.resolvedNoteText}>
                      Reset by {inc.interlock_reset_by || 'manager'}
                    </Text>
                  </View>
                )}
                {!!inc.snapshot_path && snapVisible && (
                  <ActionButton
                    label="Hide"
                    icon="image-off-outline"
                    variant="ghost"
                    compact
                    onPress={() =>
                      setOpenSnapshots((prev) => ({ ...prev, [inc.incident_id]: false }))
                    }
                  />
                )}
              </View>
            </View>
          );
        })}

        <Text style={styles.footnote}>
          Incidents are created by the gateway when helmet compliance fails or a badge breaches the
          proximity envelope. Resets are written to the audit log with the operator identity.
        </Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: PALETTE.bg },
  filters: {
    flexDirection: 'row',
    gap: 6,
    paddingHorizontal: SPACING.lg,
    paddingTop: SPACING.md,
    paddingBottom: SPACING.sm,
  },
  filter: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    borderRadius: RADIUS.pill,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    backgroundColor: PALETTE.surface,
  },
  filterActive: { backgroundColor: PALETTE.primaryContainer, borderColor: 'rgba(111,183,255,0.45)' },
  filterText: { fontFamily: FONT.sansMedium, fontSize: 12, color: PALETTE.textMuted },
  filterTextActive: { color: PALETTE.onPrimaryContainer },
  content: { paddingHorizontal: SPACING.lg, paddingTop: SPACING.sm, paddingBottom: SPACING['2xl'] * 2, gap: SPACING.md },
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
  },
  bannerText: { flex: 1, fontFamily: FONT.sans, fontSize: 12, color: PALETTE.onWarningContainer },
  card: {
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    borderRadius: RADIUS.lg,
    padding: SPACING.lg,
    gap: SPACING.md,
  },
  cardResolved: { backgroundColor: PALETTE.surfaceLow, borderColor: PALETTE.outlineSoft },
  cardHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: 1,
    borderRadius: RADIUS.pill,
    paddingHorizontal: 9,
    paddingVertical: 4,
    flexShrink: 1,
  },
  chipText: { fontFamily: FONT.sansSemiBold, fontSize: 9.5, letterSpacing: 0.8 },
  time: { fontFamily: FONT.mono, fontSize: 10.5, color: PALETTE.textFaint },
  identity: { gap: 3 },
  worker: { fontFamily: FONT.sansSemiBold, fontSize: 16, color: PALETTE.text },
  mac: { fontFamily: FONT.mono, fontSize: 10.5, color: PALETTE.textFaint },
  stats: {
    flexDirection: 'row',
    borderTopWidth: 1,
    borderTopColor: PALETTE.outlineSoft,
    paddingTop: SPACING.md,
    gap: SPACING.sm,
  },
  stat: { flex: 1, gap: 3 },
  statLabel: { fontFamily: FONT.sansMedium, fontSize: 9, letterSpacing: 1, color: PALETTE.textFaint },
  statValue: { fontFamily: FONT.monoMedium, fontSize: 13, color: PALETTE.text },
  snapshotWrap: { marginTop: 2 },
  snapshotPlaceholder: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    height: 56,
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: PALETTE.outline,
    backgroundColor: PALETTE.surfaceLow,
  },
  snapshotPlaceholderText: { fontFamily: FONT.sansMedium, fontSize: 12, color: PALETTE.textMuted },
  actions: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm },
  resolvedNote: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6 },
  resolvedNoteText: { fontFamily: FONT.sans, fontSize: 11.5, color: PALETTE.textMuted },
  footnote: {
    fontFamily: FONT.sans,
    fontSize: 11,
    lineHeight: 16,
    color: PALETTE.textFaint,
    marginTop: SPACING.xs,
  },
});
