import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import { Card, Text, ActivityIndicator } from 'react-native-paper';
import { api } from '../api';

export default function WorkersScreen() {
  const [workers, setWorkers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try { const res = await api.workers(); setWorkers(res.badges || []); } catch {} finally { setLoading(false); }
    })();
  }, []);

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} />;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text variant="headlineSmall" style={styles.title}>Authorized Badges</Text>
      {workers.length === 0 && <Text>No badges registered.</Text>}
      {workers.map((w) => (
        <Card key={w.badge_mac} style={styles.card}>
          <Card.Title title={w.worker_id} subtitle={w.worker_name} />
          <Card.Content>
            <Text>MAC: {w.badge_mac}</Text>
            <Text>Dept: {w.department}</Text>
            <Text>Active: {w.active ? 'Yes' : 'No'}</Text>
          </Card.Content>
        </Card>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({ container: { padding: 16 }, title: { marginBottom: 12 }, card: { marginBottom: 12 } });