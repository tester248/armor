import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { Card, Text, Button, ActivityIndicator, Icon, Chip, ProgressBar } from 'react-native-paper';
import { api, DEFAULT_DEVICE_ID } from '../api';
import { STATUS, SPACING } from '../theme';

export default function CalibrationScreen() {
  const [model, setModel] = useState<any>(null);
  const [anomalies, setAnomalies] = useState<any[]>([]);
  const [telemetryCount, setTelemetryCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [calibrating, setCalibrating] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [contamination, setContamination] = useState(0.05);

  const load = async () => {
    try {
      const [m, a, t] = await Promise.all([
        api.model(DEFAULT_DEVICE_ID).catch(() => null),
        api.anomalies(DEFAULT_DEVICE_ID, 10).catch(() => ({ anomalies: [] })),
        api.telemetry(DEFAULT_DEVICE_ID, 500).catch(() => ({ samples: [] })),
      ]);
      setModel(m?.model_package || null);
      setAnomalies(a?.anomalies || []);
      setTelemetryCount((t?.samples || []).length);
    } catch (e: any) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const runCalibration = async () => {
    setCalibrating(true);
    setMsg(null);
    try {
      const res = await api.calibrate(DEFAULT_DEVICE_ID, contamination);
      setMsg(`Calibration complete — ${res.window_count} windows, quality=${res.quality?.toFixed?.(3) ?? 'N/A'}`);
      await load();
    } catch (e: any) {
      setMsg(`Calibration failed: ${e.message}`);
    } finally {
      setCalibrating(false);
    }
  };

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} size="large" />;

  const hasModel = model !== null;
  const baseline = model?.baseline_stats || {};
  const pkg = typeof model?.model_package === 'string' ? JSON.parse(model.model_package) : model?.model_package || {};

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text variant="headlineSmall" style={styles.title}>Calibration & ML Model</Text>
      {msg && <Text style={styles.msg}>{msg}</Text>}

      {/* Model Status */}
      <Card style={styles.card} mode="elevated">
        <Card.Title title="Model Status" left={(p) => <Icon {...p} source="brain" />} />
        <Card.Content>
          <View style={styles.row}>
            <Text style={styles.label}>Calibrated Model</Text>
            <Chip icon={hasModel ? 'check' : 'close'} style={{ backgroundColor: hasModel ? STATUS.OK : STATUS.DANGER }} textStyle={{ color: '#fff' }}>
              {hasModel ? 'EXISTS' : 'NONE'}
            </Chip>
          </View>
          {hasModel && (
            <>
              <View style={styles.row}>
                <Text style={styles.label}>Windows</Text>
                <Text style={styles.value}>{model.window_count ?? 'N/A'}</Text>
              </View>
              <View style={styles.row}>
                <Text style={styles.label}>Quality</Text>
                <Text style={styles.value}>{(model.quality ?? 0).toFixed(3)}</Text>
              </View>
              {baseline.mean_acc !== undefined && (
                <>
                  <View style={styles.row}>
                    <Text style={styles.label}>Mean Acc</Text>
                    <Text style={styles.value}>{baseline.mean_acc?.toFixed?.(4)} g</Text>
                  </View>
                  <View style={styles.row}>
                    <Text style={styles.label}>Std Acc</Text>
                    <Text style={styles.value}>{baseline.std_acc?.toFixed?.(4)} g</Text>
                  </View>
                  <View style={styles.row}>
                    <Text style={styles.label}>Samples</Text>
                    <Text style={styles.value}>{baseline.sample_count ?? 'N/A'}</Text>
                  </View>
                </>
              )}
              {pkg.thresholds && (
                <>
                  <View style={styles.row}>
                    <Text style={styles.label}>Threshold (high)</Text>
                    <Text style={styles.value}>{pkg.thresholds.hysteresis_high?.toFixed?.(3)}</Text>
                  </View>
                  <View style={styles.row}>
                    <Text style={styles.label}>Threshold (low)</Text>
                    <Text style={styles.value}>{pkg.thresholds.hysteresis_low?.toFixed?.(3)}</Text>
                  </View>
                </>
              )}
            </>
          )}
          {!hasModel && (
            <Text style={styles.muted}>Collect 20+ telemetry samples, then run calibration below.</Text>
          )}
        </Card.Content>
      </Card>

      {/* Sample Availability */}
      <Card style={styles.card} mode="elevated">
        <Card.Title title="Sample Availability" left={(p) => <Icon {...p} source="database" />} />
        <Card.Content>
          <View style={styles.row}>
            <Text style={styles.label}>Telemetry Samples</Text>
            <Text style={styles.value}>{telemetryCount} / 20 needed</Text>
          </View>
          <ProgressBar
            progress={Math.min(telemetryCount / 20, 1)}
            color={telemetryCount >= 20 ? STATUS.OK : STATUS.WARNING}
            style={{ height: 6, marginTop: 4 }}
          />
          {telemetryCount < 20 && (
            <Text style={styles.muted}>Need {20 - telemetryCount} more samples for calibration.</Text>
          )}
        </Card.Content>
      </Card>

      {/* Run Calibration */}
      <Card style={styles.card} mode="elevated">
        <Card.Title title="Run Calibration" left={(p) => <Icon {...p} source="tune" />} />
        <Card.Content>
          <Text style={{ marginBottom: SPACING.sm, color: STATUS.MUTED }}>
            Trains IsolationForest-distilled model on real ADXL345 telemetry.
          </Text>
          <View style={styles.row}>
            <Text style={styles.label}>Contamination</Text>
            <Text style={styles.value}>{(contamination * 100).toFixed(0)}%</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: SPACING.sm }}>
            {[0.01, 0.03, 0.05, 0.1, 0.2].map((v) => (
              <Button
                key={v}
                mode={contamination === v ? 'contained' : 'outlined'}
                compact
                onPress={() => setContamination(v)}
              >
                {(v * 100).toFixed(0)}%
              </Button>
            ))}
          </View>
          <Button
            mode="contained"
            onPress={runCalibration}
            disabled={calibrating || telemetryCount < 20}
            loading={calibrating}
            style={styles.btn}
            icon="play"
          >
            Run Calibration
          </Button>
        </Card.Content>
      </Card>

      {/* Recent Anomalies */}
      <Card style={styles.card} mode="elevated">
        <Card.Title title="Recent Anomalies" left={(p) => <Icon {...p} source="alert-circle" />} />
        <Card.Content>
          {anomalies.length === 0 && <Text style={styles.muted}>No anomaly records yet. Run calibration first.</Text>}
          {anomalies.slice(0, 10).map((a, i) => (
            <View key={i} style={styles.anomalyRow}>
              <Text style={styles.anomalyScore}>{(a.anomaly_score ?? 0).toFixed(3)}</Text>
              <Text style={styles.anomalyThreshold}>thresh: {(a.threshold ?? 0).toFixed(3)}</Text>
              <Chip
                compact
                style={{ backgroundColor: a.is_anomaly ? STATUS.DANGER : STATUS.OK }}
                textStyle={{ color: '#fff', fontSize: 10 }}
              >
                {a.is_anomaly ? 'ANOMALY' : 'NOMINAL'}
              </Chip>
            </View>
          ))}
        </Card.Content>
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: SPACING.lg },
  title: { marginBottom: SPACING.md },
  card: { marginBottom: SPACING.md },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SPACING.sm },
  label: { color: STATUS.MUTED, fontSize: 14 },
  value: { color: '#f8fafc', fontSize: 15, fontWeight: '600' },
  btn: { marginTop: 4 },
  msg: { color: STATUS.INFO, marginBottom: SPACING.sm, fontSize: 13 },
  muted: { color: STATUS.MUTED, fontStyle: 'italic', fontSize: 13 },
  anomalyRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6, paddingVertical: 4 },
  anomalyScore: { fontSize: 14, fontWeight: '700', color: '#f8fafc', width: 60 },
  anomalyThreshold: { fontSize: 11, color: STATUS.MUTED, flex: 1 },
});
