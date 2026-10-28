import React, { useState } from 'react';
import { View, StyleSheet } from 'react-native';
import { Card, Text, Button, ActivityIndicator, Icon, Switch, Divider } from 'react-native-paper';
import { api, DEFAULT_DEVICE_ID } from '../api';
import { STATUS, SPACING } from '../theme';

export default function InterlockScreen() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [benchMode, setBenchMode] = useState(true);

  const send = async (command: 'LOCKOUT' | 'RESET') => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await api.interlock(command, DEFAULT_DEVICE_ID);
      setMsg(`${command} sent — motor ${command === 'LOCKOUT' ? 'locked' : 'running'}`);
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
      setMsg(`Breach posted — vision inspection triggered`);
    } catch (e: any) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.container}>
      {/* Motor Control */}
      <Card style={styles.card} mode="elevated">
        <Card.Title title="Motor Control" left={(p) => <Icon {...p} source="engine" />} />
        <Card.Content>
          <Text style={{ marginBottom: SPACING.md, color: STATUS.MUTED }}>
            Manual control of the machine cell safety interlock (L298N ENA GPIO 25).
          </Text>
          <Button
            mode="contained"
            buttonColor={STATUS.DANGER}
            onPress={() => send('LOCKOUT')}
            disabled={busy}
            style={styles.btn}
            icon="flash"
          >
            EMERGENCY LOCKOUT
          </Button>
          <Button
            mode="outlined"
            onPress={() => send('RESET')}
            disabled={busy}
            style={styles.btn}
            icon="restart"
          >
            RESET INTERLOCK
          </Button>
          <Button
            mode="contained-tonal"
            onPress={simulateBreach}
            disabled={busy}
            style={styles.btn}
            icon="walk"
          >
            Simulate Proximity Breach
          </Button>
          {busy && <ActivityIndicator style={{ marginTop: 12 }} />}
          {msg && <Text style={styles.msg}>{msg}</Text>}
        </Card.Content>
      </Card>

      {/* Bench Test Mode (replaces Blynk V5) */}
      <Card style={styles.card} mode="elevated">
        <Card.Title title="Bench Test Mode" left={(p) => <Icon {...p} source="bug" />} />
        <Card.Content>
          <Text style={{ marginBottom: SPACING.sm, color: STATUS.MUTED }}>
            Suppresses desk proximity lockouts during calibration. Maps to Blynk V5.
          </Text>
          <View style={styles.toggleRow}>
            <Text>Bench Test Mode</Text>
            <Switch
              value={benchMode}
              onValueChange={setBenchMode}
              color={STATUS.INFO}
            />
          </View>
          <Text style={{ fontSize: 12, color: STATUS.MUTED, marginTop: SPACING.xs }}>
            {benchMode ? 'ON — proximity lockouts suppressed' : 'OFF — full safety active'}
          </Text>
        </Card.Content>
      </Card>

      {/* Info */}
      <Card style={styles.card} mode="outlined">
        <Card.Content>
          <Text style={{ fontSize: 12, color: STATUS.MUTED }}>
            ⚠️ Interlock commands are sent via MQTT to the ESP32 machine node.
            Motor power cut takes &lt;50 ms (GPIO action).
          </Text>
        </Card.Content>
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: SPACING.lg },
  card: { marginBottom: SPACING.md },
  btn: { marginBottom: SPACING.sm },
  msg: { marginTop: SPACING.sm, fontSize: 12 },
  toggleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: SPACING.sm },
});
