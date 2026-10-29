import React, { useCallback, useEffect, useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { api } from '../api';
import { Divider, EmptyState, Panel } from '../components/Panel';
import ActionButton from '../components/ActionButton';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';

/** ESP32 smart-badge registry. Rendered inside the System hub. */
export default function WorkersScreen() {
  const [workers, setWorkers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showRegister, setShowRegister] = useState(false);
  const [newMac, setNewMac] = useState('');
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.workers();
      setWorkers(Array.isArray(res?.badges) ? res.badges : []);
      setMsg(null);
    } catch (e: any) {
      setMsg(e?.message || 'Could not load badges');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, [load]);

  const register = async () => {
    if (!newMac.trim() || !newId.trim()) {
      setMsg('Badge MAC and worker ID are both required.');
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await api.registerWorker(newMac.trim(), newId.trim(), newName.trim() || undefined);
      setNewMac('');
      setNewId('');
      setNewName('');
      setShowRegister(false);
      await load();
      setMsg('Badge registered.');
    } catch (e: any) {
      setMsg(e?.message || 'Registration failed');
    } finally {
      setBusy(false);
    }
  };

  const deactivate = async (mac: string) => {
    setBusy(true);
    try {
      await api.deactivateWorker(mac);
      await load();
    } catch (e: any) {
      setMsg(e?.message || 'Deactivation failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.wrap}>
      <View style={styles.head}>
        <Text style={styles.count}>
          {workers.length} badge{workers.length === 1 ? '' : 's'} registered
        </Text>
        <ActionButton
          label={showRegister ? 'Cancel' : 'Register'}
          icon={showRegister ? 'close' : 'plus'}
          variant="tonal"
          compact
          onPress={() => setShowRegister((v) => !v)}
        />
      </View>

      {!!msg && (
        <View style={styles.msg}>
          <MaterialCommunityIcons name="information-outline" size={14} color={PALETTE.info} />
          <Text style={styles.msgText}>{msg}</Text>
        </View>
      )}

      {showRegister && (
        <Panel style={styles.form}>
          <Text style={styles.formTitle}>Register a badge</Text>
          <TextInput
            value={newMac}
            onChangeText={setNewMac}
            placeholder="Badge MAC · 24:6F:28:AB:C1:02"
            placeholderTextColor={PALETTE.textFaint}
            autoCapitalize="characters"
            autoCorrect={false}
            style={styles.input}
            selectionColor={PALETTE.primary}
          />
          <TextInput
            value={newId}
            onChangeText={setNewId}
            placeholder="Worker ID · BADGE-EMP-402"
            placeholderTextColor={PALETTE.textFaint}
            autoCapitalize="characters"
            autoCorrect={false}
            style={styles.input}
            selectionColor={PALETTE.primary}
          />
          <TextInput
            value={newName}
            onChangeText={setNewName}
            placeholder="Name (optional)"
            placeholderTextColor={PALETTE.textFaint}
            style={styles.input}
            selectionColor={PALETTE.primary}
          />
          <ActionButton
            label="Register badge"
            icon="check"
            loading={busy}
            onPress={register}
            style={{ marginTop: SPACING.xs }}
          />
        </Panel>
      )}

      {loading && workers.length === 0 && <Text style={styles.muted}>Loading badge registry…</Text>}

      {!loading && workers.length === 0 && (
        <Panel>
          <EmptyState
            icon="badge-account-outline"
            title="No badges registered"
            body="Register the MAC of an ESP32 smart badge to authorise proximity tracking."
          />
        </Panel>
      )}

      {workers.map((w) => (
        <Panel key={w.badge_mac} style={styles.card}>
          <View style={styles.cardHead}>
            <View style={[styles.tile, !w.active && styles.tileOff]}>
              <MaterialCommunityIcons
                name="badge-account"
                size={20}
                color={w.active ? PALETTE.primary : PALETTE.textFaint}
              />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.workerId} numberOfLines={1}>
                {w.worker_id || 'unassigned'}
              </Text>
              <Text style={styles.workerName} numberOfLines={1}>
                {w.worker_name || 'Operator'} · {w.department || 'Fabrication'}
              </Text>
            </View>
            <View style={[styles.state, !w.active && styles.stateOff]}>
              <Text style={[styles.stateText, { color: w.active ? PALETTE.success : PALETTE.textMuted }]}>
                {w.active ? 'ACTIVE' : 'INACTIVE'}
              </Text>
            </View>
          </View>

          <Divider />

          <View style={styles.macRow}>
            <Text style={styles.macLabel}>MAC</Text>
            <Text style={styles.mac} numberOfLines={1}>
              {w.badge_mac}
            </Text>
            {w.active && (
              <Text style={styles.deactivate} onPress={() => deactivate(w.badge_mac)}>
                Deactivate
              </Text>
            )}
          </View>
        </Panel>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: SPACING.md },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  count: { fontFamily: FONT.sans, fontSize: 12, color: PALETTE.textMuted },
  msg: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingHorizontal: SPACING.md,
    paddingVertical: 8,
    borderRadius: RADIUS.md,
    backgroundColor: 'rgba(111,183,255,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(111,183,255,0.24)',
  },
  msgText: { flex: 1, fontFamily: FONT.sans, fontSize: 12, color: PALETTE.info },
  form: { gap: SPACING.sm },
  formTitle: { fontFamily: FONT.sansSemiBold, fontSize: 14, color: PALETTE.text },
  input: {
    fontFamily: FONT.mono,
    fontSize: 12.5,
    color: PALETTE.text,
    backgroundColor: PALETTE.surfaceContainer,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    borderRadius: RADIUS.sm,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  muted: { fontFamily: FONT.sans, fontSize: 12, color: PALETTE.textMuted, textAlign: 'center' },
  card: { gap: SPACING.md },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: SPACING.md },
  tile: {
    width: 40,
    height: 40,
    borderRadius: RADIUS.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(111,183,255,0.10)',
    borderWidth: 1,
    borderColor: 'rgba(111,183,255,0.26)',
  },
  tileOff: { backgroundColor: PALETTE.surfaceContainer, borderColor: PALETTE.outlineSoft },
  workerId: { fontFamily: FONT.sansSemiBold, fontSize: 15, color: PALETTE.text },
  workerName: { fontFamily: FONT.sans, fontSize: 11.5, color: PALETTE.textMuted, marginTop: 2 },
  state: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: RADIUS.pill,
    backgroundColor: 'rgba(69,212,138,0.10)',
    borderWidth: 1,
    borderColor: 'rgba(69,212,138,0.30)',
  },
  stateOff: { backgroundColor: 'transparent', borderColor: PALETTE.outlineSoft },
  stateText: { fontFamily: FONT.sansSemiBold, fontSize: 9, letterSpacing: 0.9 },
  macRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  macLabel: { fontFamily: FONT.sansMedium, fontSize: 10, letterSpacing: 1, color: PALETTE.textFaint },
  mac: { flex: 1, fontFamily: FONT.mono, fontSize: 11, color: PALETTE.textMuted },
  deactivate: { fontFamily: FONT.sansMedium, fontSize: 11.5, color: PALETTE.danger },
});
