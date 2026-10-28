import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import { Card, Text, ActivityIndicator, Chip, Icon } from 'react-native-paper';
import { api, DEFAULT_DEVICE_ID } from '../api';

export default function DashboardScreen() {
  const [status, setStatus] = useState<any>(null);
  const [telemetry, setTelemetry] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const [s, t] = await Promise.all([api.status(DEFAULT_DEVICE_ID), api.telemetry(DEFAULT_DEVICE_ID, 30)]);
      setStatus(s);
      setTelemetry(t.samples || []);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, []);

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} />;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text variant="headlineSmall" style={styles.title}>Live Telemetry</Text>
      {error && <Text style={styles.error}>{error}</Text>}
      {status && (
        <Card style={styles.card}>
          <Card.Title title="Machine Status" left={(p) => <Icon {...p} source="engine" />} />
          <Card.Content>
            <Text>Motor: {status.motor_state}</Text>
            <Text>Interlock: {status.interlock_active ? 'ACTIVE' : 'clear'}</Text>
            <Text>RMS: {status.current_rms?.toFixed?.(3)} g</Text>
            <Text>Voltage: {status.current_voltage_v?.toFixed?.(2)} V</Text>
            <Text>Current: {status.current_ma?.toFixed?.(1)} mA</Text>
            <Text>Temp: {status.current_temp_c?.toFixed?.(1)} °C</Text>
            <Text>Worker: {status.active_worker_id || '—'}</Text>
            <Chip style={{ marginTop: 8 }} icon={status.proximity_breach_active ? 'alert' : 'check'}>{status.proximity_breach_active ? 'BREACH' : 'CLEAR'}</Chip>
          </Card.Content>
        </Card>
      )}
      <Card style={styles.card}>
        <Card.Title title="Recent Samples" />
        <Card.Content>
          {telemetry.slice(-10).reverse().map((s, i) => (
            <Text key={i} style={styles.sample}>
              {s.ts} — RMS {s.rms?.toFixed?.(3)} g · {s.temperature_c?.toFixed?.(1)}°C · {s.voltage_v?.toFixed?.(2)}V
            </Text>
          ))}
          {telemetry.length === 0 && <Text>No telemetry yet.</Text>}
        </Card.Content>
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16 },
  title: { marginBottom: 12 },
  card: { marginBottom: 12 },
  sample: { fontSize: 12, marginBottom: 4 },
  error: { color: '#ef4444', marginBottom: 8 },
});