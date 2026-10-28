import React, { useEffect, useState, useCallback } from 'react';
import { View, StyleSheet, ActivityIndicator } from 'react-native';
import { Card, Text, Button, Icon, Chip } from 'react-native-paper';
import { WebView } from 'react-native-webview';
import { api, DEFAULT_DEVICE_ID, WS_BASE } from '../api';
import { STATUS, SPACING } from '../theme';

const STREAM_URL = (process.env.EXPO_PUBLIC_ARMOR_API_URL || 'http://10.0.2.2:8000') + '/video/stream';

export default function VisionScreen() {
  const [inspecting, setInspecting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);

  // Poll inspection status when running
  useEffect(() => {
    if (!polling) return;
    const id = setInterval(async () => {
      try {
        const res = await api.visionInspectStatus();
        const status = res?.status;
        if (status === 'complete' && res?.result) {
          setResult(res.result);
          setInspecting(false);
          setPolling(false);
          clearInterval(id);
        } else if (status === 'waiting_for_person') {
          // still waiting
        } else if (status === 'processing') {
          // processing
        }
      } catch (e: any) {
        setError(e.message);
        setInspecting(false);
        setPolling(false);
        clearInterval(id);
      }
    }, 1000);
    return () => clearInterval(id);
  }, [polling]);

  const runInspection = async () => {
    setInspecting(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.visionInspectStart('WORKER_EMP_402', DEFAULT_DEVICE_ID);
      if (res?.status === 'started') {
        setPolling(true);
      } else {
        setError('Failed to start inspection');
        setInspecting(false);
      }
    } catch (e: any) {
      setError(e.message);
      setInspecting(false);
    }
  };

  const clearResult = () => {
    setResult(null);
    setInspecting(false);
    setPolling(false);
  };

  const snapshotUrl = result?.snapshot_path
    ? `${process.env.EXPO_PUBLIC_ARMOR_API_URL || 'http://10.0.2.2:8000'}/api/v1/vision/snapshot/${result.snapshot_path.split('/').pop()}`
    : null;

  return (
    <View style={styles.container}>
      {/* Live Camera Feed */}
      <Card style={styles.card} mode="elevated">
        <Card.Title title="Live Camera" left={(p) => <Icon {...p} source="video" />} />
        <Card.Content>
          <View style={styles.feedContainer}>
            <WebView
              source={{ html: `<img src="${STREAM_URL}" style="width:100%;height:100%;object-fit:contain;" />` }}
              style={styles.webview}
              scrollEnabled={false}
              scalesPageToFit={false}
            />
          </View>
        </Card.Content>
      </Card>

      {/* Helmet Inspection Controls */}
      <Card style={styles.card} mode="elevated">
        <Card.Title title="Helmet Inspection" left={(p) => <Icon {...p} source="shield-search" />} />
        <Card.Content>
          <Button
            mode="contained"
            onPress={runInspection}
            disabled={inspecting}
            style={styles.btn}
            icon="play"
          >
            {polling ? (result ? 'Inspection Complete' : 'Waiting for person...') : 'Run Helmet Inspection'}
          </Button>
          {inspecting && !result && (
            <View style={styles.statusRow}>
              <ActivityIndicator size="small" />
              <Text style={{ marginLeft: 8, color: STATUS.INFO }}>
                {polling ? 'Waiting for person in camera...' : 'Starting...'}
              </Text>
            </View>
          )}
          {error && <Text style={styles.error}>{error}</Text>}

          {/* Result display */}
          {result && (
            <View style={styles.resultBox}>
              <View style={styles.resultHeader}>
                <Chip
                  icon={result.compliant ? 'check-circle' : result.compliant === null ? 'help-circle' : 'close-circle'}
                  style={{ backgroundColor: result.compliant ? STATUS.OK : result.compliant === null ? STATUS.WARNING : STATUS.DANGER }}
                  textStyle={{ color: '#fff' }}
                >
                  {result.compliant ? 'HELMET PASS' : result.compliant === null ? 'SCANNING' : 'HELMET FAIL'}
                </Chip>
              </View>
              <Text style={styles.resultText}>
                Compliance: {(result.compliance_ratio * 100).toFixed(1)}%
              </Text>
              <Text style={styles.resultText}>
                Worker: {result.worker_id} | {result.timestamp?.slice(0, 19)}
              </Text>
              {snapshotUrl && (
                <View style={styles.snapshotContainer}>
                  <Text style={styles.label}>Result Snapshot:</Text>
                  <WebView
                    source={{ html: `<img src="${snapshotUrl}" style="width:100%;height:100%;object-fit:contain;" />` }}
                    style={styles.snapshotWebview}
                    scrollEnabled={false}
                  />
                </View>
              )}
              <Button
                mode="outlined"
                onPress={clearResult}
                style={{ marginTop: 8 }}
                icon="close"
              >
                Clear Result
              </Button>
            </View>
          )}
        </Card.Content>
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: SPACING.lg },
  card: { marginBottom: SPACING.md },
  feedContainer: { height: 280, borderRadius: 8, overflow: 'hidden', backgroundColor: '#020617' },
  webview: { flex: 1, backgroundColor: '#020617' },
  btn: { marginBottom: SPACING.sm },
  statusRow: { flexDirection: 'row', alignItems: 'center', marginTop: 8 },
  resultBox: { marginTop: SPACING.md, padding: SPACING.md, borderRadius: 8, backgroundColor: '#1e293b' },
  resultHeader: { marginBottom: SPACING.sm },
  resultText: { fontSize: 13, color: '#f8fafc', marginBottom: 2 },
  snapshotContainer: { height: 200, marginTop: SPACING.sm, borderRadius: 8, overflow: 'hidden' },
  snapshotWebview: { flex: 1, backgroundColor: '#020617' },
  label: { fontSize: 12, color: STATUS.MUTED, marginBottom: 4 },
  error: { color: STATUS.DANGER, marginTop: 8 },
});
