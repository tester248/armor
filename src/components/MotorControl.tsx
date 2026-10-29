import React, { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { Switch, Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { api, DEFAULT_DEVICE_ID } from '../api';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';
import ActionButton from './ActionButton';

type Props = {
  status: any;
  onChanged?: () => void;
};

/**
 * Real motor control: START/STOP go to POST /api/v1/interlock, which the
 * gateway republishes on the machine node's MQTT interlock topic. The firmware
 * only energises the L298N when ``motor_requested && !interlock``, so an active
 * lockout always wins — the backend also rejects START with 409.
 */
export default function MotorControl({ status, onChanged }: Props) {
  const reported: boolean = status?.motor_state === 'RUNNING';
  const locked = !!status?.interlock_active;

  const [pending, setPending] = useState<null | 'START' | 'STOP'>(null);
  const [optimistic, setOptimistic] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reconcile with the polled status once the gateway catches up.
  useEffect(() => {
    setOptimistic(null);
  }, [reported, locked]);

  const running = optimistic ?? reported;

  const send = async (command: 'START' | 'STOP') => {
    setPending(command);
    setError(null);
    try {
      await api.interlock(command, DEFAULT_DEVICE_ID);
      setOptimistic(command === 'START');
      onChanged?.();
    } catch (e: any) {
      setOptimistic(null);
      setError(e?.message || 'Could not reach the machine node');
    } finally {
      setPending(null);
    }
  };

  const toggle = () => {
    if (pending) return;
    if (!running && locked) {
      setError('Interlock is active. Reset the lockout before starting the motor.');
      return;
    }
    send(running ? 'STOP' : 'START');
  };

  const stateLabel = locked ? 'LOCKED OUT' : running ? 'RUNNING' : 'IDLE';
  const stateColor = locked ? PALETTE.danger : running ? PALETTE.success : PALETTE.textMuted;

  return (
    <View style={styles.card}>
      <View style={styles.head}>
        <View style={[styles.tile, locked && styles.tileLocked]}>
          <MaterialCommunityIcons
            name={locked ? 'lock-outline' : 'engine-outline'}
            size={24}
            color={locked ? PALETTE.danger : PALETTE.primary}
          />
        </View>

        <View style={styles.headText}>
          <Text style={styles.title}>Motor power</Text>
          <View style={styles.stateRow}>
            <View style={[styles.stateDot, { backgroundColor: stateColor }]} />
            <Text style={[styles.state, { color: stateColor }]}>{stateLabel}</Text>
            <Text style={styles.stateMeta}>· RS-555 via L298N</Text>
          </View>
        </View>

        <Switch
          value={running}
          onValueChange={toggle}
          disabled={!!pending || (locked && !running)}
          color={PALETTE.primary}
          accessibilityLabel="Motor power switch"
        />
      </View>

      <Text style={styles.helper}>
        {locked
          ? 'Interlocks still apply. The gateway refuses START while a lockout is active.'
          : 'Starts the RS-555 drive. Safety interlocks still override this switch.'}
      </Text>

      {!!error && (
        <View style={styles.errorRow}>
          <MaterialCommunityIcons name="alert-circle-outline" size={14} color={PALETTE.warning} />
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      <ActionButton
        variant={running ? 'outline' : 'filled'}
        icon={running ? 'stop-circle-outline' : 'play-circle-outline'}
        label={
          pending
            ? pending === 'START'
              ? 'Starting motor…'
              : 'Stopping motor…'
            : locked
              ? 'Interlock active — reset first'
              : running
                ? 'Motor running · tap to stop'
                : 'Start motor'
        }
        loading={!!pending}
        disabled={locked && !running}
        onPress={toggle}
        style={styles.action}
        accessibilityHint="Sends a START or STOP command to the machine node"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    borderRadius: RADIUS.lg,
    padding: SPACING.lg,
    gap: SPACING.md,
  },
  head: { flexDirection: 'row', alignItems: 'center', gap: SPACING.md },
  tile: {
    width: 46,
    height: 46,
    borderRadius: RADIUS.md,
    backgroundColor: 'rgba(111,183,255,0.10)',
    borderWidth: 1,
    borderColor: 'rgba(111,183,255,0.28)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  tileLocked: {
    backgroundColor: 'rgba(255,107,107,0.10)',
    borderColor: 'rgba(255,107,107,0.32)',
  },
  headText: { flex: 1, minWidth: 0 },
  title: { fontFamily: FONT.sansSemiBold, fontSize: 16, color: PALETTE.text },
  stateRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 3 },
  stateDot: { width: 6, height: 6, borderRadius: 3 },
  state: { fontFamily: FONT.sansSemiBold, fontSize: 11.5, letterSpacing: 0.8 },
  stateMeta: { fontFamily: FONT.sans, fontSize: 11, color: PALETTE.textFaint, flexShrink: 1 },
  helper: {
    fontFamily: FONT.sans,
    fontSize: 12.5,
    lineHeight: 18,
    color: PALETTE.textMuted,
  },
  errorRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 7 },
  errorText: {
    flex: 1,
    fontFamily: FONT.sans,
    fontSize: 12,
    lineHeight: 17,
    color: PALETTE.warning,
  },
  action: { marginTop: 2 },
});
