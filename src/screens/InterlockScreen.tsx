import React, { useState, useEffect } from 'react';
import { View, StyleSheet } from 'react-native';
import { Card, Text, Button, ActivityIndicator, Icon, Switch, Divider, Chip } from 'react-native-paper';
import { api, DEFAULT_DEVICE_ID } from '../api';
import { STATUS, SPACING } from '../theme';

export default function InterlockScreen() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [benchMode, setBenchMode] = useState(true);
  const [debugMode, setDebugMode] = useState(false);
  const [mqttMsgs, setMqttMsgs] = useState<any[]>([]);

  const send = async (command: 'LOCKOUT' | 'RESET') => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await api.interlock(command, DEFAULT_DEVICE_ID);
      setMsg(`${command} sent — motor ${command === 'LOCKOUT' ? 'LOCKED' : 'RUNNING'}`);
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
      setMsg(`Proximity breach triggered — vision inspection triggered`);
    } catch (e: any) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const toggleBenchMode = async (value: boolean) => {
    setBenchMode(value);
    setMsg(`Bench Test Mode: ${value ? 'ON — proximity lockouts suppressed' : 'OFF — full safety active'}`);
  };

  const toggleDebugMode = (value: boolean) => {
    setDebugMode(value);
    if (value) {
      loadMqttDebug();
    }
  };

  const loadMqttDebug = async () => {
    try {
      const res = await api.debugMqtt(10);
      setMqttMsgs(res.messages || []);
    } catch (e: any) {
      setMsg(`Debug error: ${e.message}`);
    }
  };

  return (
    <View style={styles.container}>
      {/* Motor Control */}
      <Card style={styles.card} mode="contained">
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
      <Card style={styles.card} mode="contained">
        <Card.Title title="Bench Test Mode" left={(p) => <Icon {...p} source="bug" />} />
        <Card.Content>
          <Text style={{ marginBottom: SPACING.sm, color: STATUS.MUTED }}>
            Suppresses desk proximity lockouts during calibration. Maps to Blynk V5.
          </Text>
          <View style={styles.toggleRow}>
            <Text style={{ fontSize: 15 }}>Bench Test Mode</Text>
            <Switch
              value={benchMode}
              onValueChange={toggleBenchMode}
              color={STATUS.INFO}
            />
          </View>
          <Text style={{ fontSize: 12, color: STATUS.MUTED, marginTop: SPACING.xs }}>
            {benchMode ? 'ON — proximity lockouts suppressed' : 'OFF — full safety active'}
          </Text>
        </Card.Content>
      </Card>

      {/* Debug Mode (replaces Blynk debug) */}
      <Card style={styles.card} mode="contained">
        <Card.Title title="Debug Mode" left={(p) => <Icon {...p} source="bug-outline" />} />
        <Card.Content>
          <View style={styles.toggleRow}>
            <Text style={{ fontSize: 15 }}>Debug Mode</Text>
            <Switch
              value={debugMode}
              onValueChange={toggleDebugMode}
              color={STATUS.INFO}
            />
          </View>
          {debugMode && (
            <>
              <Divider style={{ marginVertical: SPACING.sm }} />
              <Text style={{ fontSize: 13, color: STATUS.MUTED, marginBottom: SPACING.sm }}>
                Recent MQTT Messages:
              </Text>
              {mqttMsgs.length === 0 ? (
                <Text style={{ fontSize: 12, color: STATUS.MUTED, fontStyle: 'italic' }}>
                  No MQTT messages yet.
                </Text>
              ) : (
                mqttMsgs.slice(0, 10).map((m, i) => (
                  <View key={i} style={styles.msgRow}>
                    <Text style={styles.msgTopic}>{m.topic || 'unknown'}</Text>
                    <Text style={styles.msgPayload}>{typeof m.payload === 'string' ? m.payload : JSON.stringify(m.payload)}</Text>
                  </View>
                ))
              )}
            </>
          )}
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
  msgRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 2, borderBottomWidth: 1, borderBottomColor: '#334155' },
  msgTopic: { fontSize: 11, color: '#06b6d4', fontWeight: '600', flex: 1 },
  msgPayload: { fontSize: 10, color: '#cbd5e1', flex: 2, fontFamily: 'monospace' },
});
