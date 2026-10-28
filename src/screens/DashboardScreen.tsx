import React, { useEffect, useState, useCallback } from 'react';
import { ScrollView, StyleSheet, View, RefreshControl } from 'react-native';
import { Card, Text, ActivityIndicator, Chip, Icon, ProgressBar } from 'react-native-paper';
import { api, DEFAULT_DEVICE_ID, WS_BASE } from '../api';
import { STATUS, SPACING } from '../theme';

export default function DashboardScreen() {
  const [status, setStatus] = useState<any>(null);
  const [telemetry, setTelemetry] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([
        api.status(DEFAULT_DEVICE_ID),
        api.telemetry(DEFAULT_DEVICE_ID, 20),
      ]);
      setStatus(s);
      setTelemetry(t.samples || []);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [load]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    load();
  }, [load]);

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} size="large" />;

  const isAnomaly = status?.is_anomaly === true;
  const rms = status?.current_rms ?? 0;
  const vibeWarn = rms > 0.15;

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      <Text variant="headlineSmall" style={styles.title}>Live Telemetry</Text>
      {error && <Text style={styles.error}>{error}</Text>}

      {/* Machine Status Card */}
      {status && (
        <Card style={styles.card} mode="elevated">
          <Card.Title
            title="Machine Status"
            left={(p) => <Icon {...p} source="engine" />}
          />
          <Card.Content>
            <View style={styles.row}>
              <Text style={styles.label}>Motor</Text>
              <Chip
                icon={status.motor_state === 'RUNNING' ? 'play' : status.motor_state === 'LOCKED' ? 'lock' : 'pause'}
                style={[styles.chip, { backgroundColor: status.motor_state === 'RUNNING' ? STATUS.OK : status.motor_state === 'LOCKED' ? STATUS.DANGER : STATUS.MUTED }]}
                textStyle={{ color: '#fff' }}
              >
                {status.motor_state}
              </Chip>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Interlock</Text>
              <Chip icon={status.interlock_active ? 'lock' : 'lock-open'} style={{ backgroundColor: status.interlock_active ? STATUS.DANGER : STATUS.OK }} textStyle={{ color: '#fff' }}>
                {status.interlock_active ? 'ACTIVE' : 'CLEAR'}
              </Chip>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Perimeter</Text>
              <Chip icon={status.proximity_breach_active ? 'alert' : 'check'} style={{ backgroundColor: status.proximity_breach_active ? STATUS.WARNING : STATUS.OK }} textStyle={{ color: '#fff' }}>
                {status.proximity_breach_active ? 'BREACH' : 'CLEAR'}
              </Chip>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Worker</Text>
              <Text style={styles.value}>{status.active_worker_id || '—'}</Text>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Anomaly</Text>
              <Chip icon={isAnomaly ? 'alert-circle' : 'check-circle'} style={{ backgroundColor: isAnomaly ? STATUS.DANGER : STATUS.OK }} textStyle={{ color: '#fff' }}>
                {isAnomaly ? 'DETECTED' : 'NOMINAL'}
              </Chip>
            </View>
          </Card.Content>
        </Card>
      )}

      {/* Sensor Readings Card */}
      {status && (
        <Card style={styles.card} mode="elevated">
          <Card.Title title="Sensor Readings" left={(p) => <Icon {...p} source="gauge" />} />
          <Card.Content>
            <View style={styles.row}>
              <Text style={styles.label}>Vibration RMS</Text>
              <Text style={[styles.value, vibeWarn ? styles.warn : null]}>{rms?.toFixed?.(3) ?? '--'} g</Text>
            </View>
            {vibeWarn && <ProgressBar progress={Math.min(rms / 0.5, 1)} color={STATUS.DANGER} style={{ height: 4, marginBottom: 8 }} />}
            <View style={styles.row}>
              <Text style={styles.label}>Bus Voltage</Text>
              <Text style={styles.value}>{status.current_voltage_v?.toFixed?.(2) ?? '--'} V</Text>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Current Draw</Text>
              <Text style={styles.value}>{status.current_ma?.toFixed?.(1) ?? '--'} mA</Text>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Temperature</Text>
              <Text style={styles.value}>{status.current_temp_c?.toFixed?.(1) ?? '--'} °C</Text>
            </View>
          </Card.Content>
        </Card>
      )}

      {/* Recent Samples Card */}
      <Card style={styles.card} mode="elevated">
        <Card.Title title="Recent Samples" left={(p) => <Icon {...p} source="chart-line" />} />
        <Card.Content>
          {telemetry.length === 0 && <Text style={styles.muted}>No telemetry yet.</Text>}
          {telemetry.slice(-10).reverse().map((s, i) => (
            <View key={i} style={styles.sampleRow}>
              <Text style={styles.sampleTime}>{(s.ts || '').slice(11, 19)}</Text>
              <Text style={styles.sampleVal}>RMS {s.rms?.toFixed?.(3)}g</Text>
              <Text style={styles.sampleVal}>{s.temperature_c?.toFixed?.(1)}°C</Text>
              <Text style={styles.sampleVal}>{s.voltage_v?.toFixed?.(2)}V</Text>
            </View>
          ))}
        </Card.Content>
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: SPACING.lg },
  title: { marginBottom: SPACING.md },
  card: { marginBottom: SPACING.md },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SPACING.sm },
  label: { color: STATUS.MUTED, fontSize: 14 },
  value: { color: '#f8fafc', fontSize: 15, fontWeight: '600' },
  chip: { paddingHorizontal: 4 },
  sampleRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 2 },
  sampleTime: { fontSize: 11, color: STATUS.MUTED, width: 70 },
  sampleVal: { fontSize: 11, color: '#f8fafc' },
  error: { color: STATUS.DANGER, marginBottom: SPACING.sm },
  muted: { color: STATUS.MUTED, fontStyle: 'italic' },
  warn: { color: STATUS.DANGER },
});
