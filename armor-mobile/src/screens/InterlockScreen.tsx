import React, { useState } from 'react';
import { View, StyleSheet } from 'react-native';
import { Card, Text, Button, ActivityIndicator, Icon } from 'react-native-paper';
import { api, DEFAULT_DEVICE_ID } from '../api';

export default function InterlockScreen() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const send = async (command: 'LOCKOUT' | 'RESET') => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await api.interlock(command, DEFAULT_DEVICE_ID);
      setMsg(`${command} sent: ${JSON.stringify(res)}`);
    } catch (e: any) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const simulateBreach = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await api.breach(DEFAULT_DEVICE_ID, 'WORKER_EMP_402', '24:6F:28:AB:C1:02');
      setMsg(`Breach posted: ${JSON.stringify(res)}`);
    } catch (e: any) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.container}>
      <Card style={styles.card}>
        <Card.Title title="Emergency Interlock" left={(p) => <Icon {...p} source="lock" />} />
        <Card.Content>
          <Text style={{ marginBottom: 12 }}>Manual control of the machine cell safety interlock.</Text>
          <Button mode="contained" buttonColor="#ef4444" onPress={() => send('LOCKOUT')} disabled={busy} style={styles.btn} icon="flash">
            EMERGENCY LOCKOUT
          </Button>
          <Button mode="outlined" onPress={() => send('RESET')} disabled={busy} style={styles.btn} icon="restart">
            RESET INTERLOCK
          </Button>
          <Button mode="contained-tonal" onPress={simulateBreach} disabled={busy} style={styles.btn} icon="walk">
            Simulate Proximity Breach
          </Button>
          {busy && <ActivityIndicator style={{ marginTop: 12 }} />}
          {msg && <Text style={styles.msg}>{msg}</Text>}
        </Card.Content>
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  card: { marginBottom: 12 },
  btn: { marginBottom: 8 },
  msg: { marginTop: 8, fontSize: 12 },
});