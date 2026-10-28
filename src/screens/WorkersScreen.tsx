import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, View, Alert } from 'react-native';
import { Card, Text, ActivityIndicator, Icon, Button, TextInput, Chip } from 'react-native-paper';
import { api } from '../api';
import { STATUS, SPACING } from '../theme';

export default function WorkersScreen() {
  const [workers, setWorkers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showRegister, setShowRegister] = useState(false);
  const [newMac, setNewMac] = useState('');
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');

  const load = async () => {
    try {
      const res = await api.workers();
      setWorkers(res.badges || []);
    } catch (e) {
      // silently fail
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const register = async () => {
    if (!newMac || !newId) {
      Alert.alert('Error', 'Badge MAC and Worker ID are required');
      return;
    }
    try {
      await api.registerWorker(newMac, newId, newName || undefined);
      setNewMac('');
      setNewId('');
      setNewName('');
      setShowRegister(false);
      await load();
    } catch (e: any) {
      Alert.alert('Error', e.message);
    }
  };

  const deactivate = async (mac: string) => {
    Alert.alert('Deactivate Badge', `Deactivate badge ${mac}?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Deactivate',
        style: 'destructive',
        onPress: async () => {
          try {
            await api.deactivateWorker(mac);
            await load();
          } catch (e: any) {
            Alert.alert('Error', e.message);
          }
        },
      },
    ]);
  };

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} size="large" />;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text variant="headlineSmall" style={styles.title}>Authorized Badges</Text>

      <Button
        mode="contained-tonal"
        onPress={() => setShowRegister(!showRegister)}
        style={{ marginBottom: SPACING.md }}
        icon={showRegister ? 'close' : 'plus'}
      >
        {showRegister ? 'Cancel' : 'Register New Badge'}
      </Button>

      {showRegister && (
        <Card style={styles.card} mode="elevated">
          <Card.Title title="Register Badge" />
          <Card.Content>
            <TextInput label="Badge MAC (e.g. 24:6F:28:AB:C1:02)" value={newMac} onChangeText={setNewMac} style={styles.input} />
            <TextInput label="Worker ID (e.g. BADGE-EMP-402)" value={newId} onChangeText={setNewId} style={styles.input} />
            <TextInput label="Worker Name (optional)" value={newName} onChangeText={setNewName} style={styles.input} />
            <Button mode="contained" onPress={register} style={{ marginTop: SPACING.sm }} icon="check">
              Register
            </Button>
          </Card.Content>
        </Card>
      )}

      {workers.length === 0 && <Text style={styles.muted}>No badges registered.</Text>}

      {workers.map((w) => (
        <Card key={w.badge_mac} style={styles.card} mode="elevated">
          <Card.Title title={w.worker_id} subtitle={w.worker_name || 'Operator'} />
          <Card.Content>
            <View style={styles.row}>
              <Text style={styles.label}>MAC</Text>
              <Text style={styles.value}>{w.badge_mac}</Text>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Department</Text>
              <Text style={styles.value}>{w.department || '—'}</Text>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Status</Text>
              <Chip compact style={{ backgroundColor: w.active ? STATUS.OK : STATUS.DANGER }} textStyle={{ color: '#fff', fontSize: 10 }}>
                {w.active ? 'Active' : 'Inactive'}
              </Chip>
            </View>
          </Card.Content>
          {w.active && (
            <Card.Actions>
              <Button onPress={() => deactivate(w.badge_mac)} icon="close-circle" textColor={STATUS.DANGER}>
                Deactivate
              </Button>
            </Card.Actions>
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
  input: { marginBottom: SPACING.sm },
  muted: { color: STATUS.MUTED, fontStyle: 'italic' },
});
