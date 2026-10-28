import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, View, Image } from 'react-native';
import { Card, Text, Button, ActivityIndicator, Icon, Chip } from 'react-native-paper';
import { api, DEFAULT_DEVICE_ID } from '../api';
import { STATUS, SPACING } from '../theme';

const API_BASE = process.env.EXPO_PUBLIC_ARMOR_API_URL || 'http://10.0.2.2:8000';

export default function IncidentsScreen() {
  const [incidents, setIncidents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = async () => {
    try {
      const res = await api.incidents(DEFAULT_DEVICE_ID);
      setIncidents(res.incidents || []);
    } catch (e) {
      // silently fail
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, []);

  const reset = async (id: string) => {
    try {
      await api.resetIncident(id, DEFAULT_DEVICE_ID);
      await load();
    } catch (e) {
      // silently fail
    }
  };

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} size="large" />;

  const selected = selectedId ? incidents.find((i) => i.incident_id === selectedId) : null;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text variant="headlineSmall" style={styles.title}>Safety Incidents</Text>
      {incidents.length === 0 && <Text style={styles.muted}>No incidents recorded.</Text>}

      {incidents.map((inc) => (
        <Card key={inc.incident_id} style={styles.card} mode="contained">
          <Card.Title
            title={`Incident ${(inc.incident_id || '').slice(0, 8)}`}
            subtitle={inc.worker_id || 'UNKNOWN'}
            left={(p) => <Icon {...p} source="clipboard-alert" />}
          />
          <Card.Content>
            <View style={styles.row}>
              <Text style={styles.label}>Violation</Text>
              <Text style={styles.value}>{inc.violation_type}</Text>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Compliance</Text>
              <Text style={styles.value}>{((inc.compliance_ratio || 0) * 100).toFixed(0)}%</Text>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Lockout</Text>
              <Chip compact style={{ backgroundColor: inc.interlock_issued ? STATUS.DANGER : STATUS.MUTED }} textStyle={{ color: '#fff', fontSize: 10 }}>
                {inc.interlock_issued ? 'Issued' : 'No'}
              </Chip>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Status</Text>
              <Chip compact style={{ backgroundColor: inc.resolved ? STATUS.OK : STATUS.DANGER }} textStyle={{ color: '#fff', fontSize: 10 }}>
                {inc.resolved ? 'Resolved' : 'OPEN'}
              </Chip>
            </View>
            <Text style={styles.time}>{(inc.created_at || '').slice(0, 19).replace('T', ' ')}</Text>
          </Card.Content>
          {!inc.resolved && (
            <Card.Actions>
              <Button onPress={() => reset(inc.incident_id)} icon="lock-open" mode="contained-tonal">
                Authorize Reset
              </Button>
              <Button onPress={() => setSelectedId(inc.incident_id === selectedId ? null : inc.incident_id)} icon="image">
                {selectedId === inc.incident_id ? 'Hide' : 'View'} Snapshot
              </Button>
            </Card.Actions>
          )}
          {selectedId === inc.incident_id && inc.snapshot_path && (
            <Card.Content>
              <Image
                source={{ uri: `${API_BASE}/api/v1/vision/snapshot/${inc.snapshot_path.split('/').pop()}` }}
                style={styles.snapshot}
                resizeMode="contain"
              />
            </Card.Content>
          )}
        </Card>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: SPACING.lg },
  title: { marginBottom: SPACING.md },
  card: { marginBottom: SPACING.md },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SPACING.xs },
  label: { color: STATUS.MUTED, fontSize: 13 },
  value: { color: '#f8fafc', fontSize: 14, fontWeight: '600' },
  time: { fontSize: 11, color: STATUS.MUTED, marginTop: 4 },
  snapshot: { width: '100%', height: 200, borderRadius: 8, backgroundColor: '#020617' },
  muted: { color: STATUS.MUTED, fontStyle: 'italic' },
});
