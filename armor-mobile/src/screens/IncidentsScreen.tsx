import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { Card, Text, Button, ActivityIndicator } from 'react-native-paper';
import { api, DEFAULT_DEVICE_ID } from '../api';

export default function IncidentsScreen() {
  const [incidents, setIncidents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const res = await api.incidents(DEFAULT_DEVICE_ID);
      setIncidents(res.incidents || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); const id = setInterval(load, 4000); return () => clearInterval(id); }, []);

  const reset = async (id: string) => {
    try { await api.resetIncident(id, DEFAULT_DEVICE_ID); await load(); } catch {}
  };

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} />;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text variant="headlineSmall" style={styles.title}>Safety Incidents</Text>
      {incidents.length === 0 && <Text>No incidents recorded.</Text>}
      {incidents.map((inc) => (
        <Card key={inc.incident_id} style={styles.card}>
          <Card.Title title={`Incident ${inc.incident_id.slice(0, 8)}`} subtitle={inc.worker_id} />
          <Card.Content>
            <Text>Violation: {inc.violation_type}</Text>
            <Text>Compliance: {(inc.compliance_ratio * 100).toFixed(0)}%</Text>
            <Text>Status: {inc.resolved ? 'Resolved' : 'OPEN'}</Text>
            <Text>Time: {inc.created_at}</Text>
          </Card.Content>
          {!inc.resolved && (
            <Card.Actions>
              <Button onPress={() => reset(inc.incident_id)} icon="lock-open">Authorize Reset</Button>
            </Card.Actions>
          )}
        </Card>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({ container: { padding: 16 }, title: { marginBottom: 12 }, card: { marginBottom: 12 } });