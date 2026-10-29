import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { api, visionFrameUrl } from '../api';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';

const FRAME_INTERVAL_MS = 420;
const STATUS_INTERVAL_MS = 6000;

export type VisionStatus = {
  camera_available: boolean;
  camera_source?: string;
  roboflow_configured?: boolean;
  vision_state?: string;
  frame_ready?: boolean;
  error?: string;
};

/**
 * The gateway exposes a single JPEG per request because React Native's Image
 * cannot decode multipart MJPEG on Android/iOS. Polling also gives us a real
 * offline signal instead of a black rectangle.
 */
export default function CameraFeed({
  onStatus,
}: {
  onStatus?: (status: VisionStatus | null) => void;
}) {
  const [status, setStatus] = useState<VisionStatus | null>(null);
  const [uri, setUri] = useState<string | null>(null);
  const [frameError, setFrameError] = useState(false);
  const [lastFrameAt, setLastFrameAt] = useState<number | null>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [nowMs, setNowMs] = useState(0);
  const errorStreak = useRef(0);

  // Drives the "frame Ns ago" readout. The clock lives in state so render stays
  // a pure function of props/state instead of calling Date.now() inline.
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      const s: VisionStatus = await api.visionStatus();
      setStatus(s);
      onStatus?.(s);
    } catch (e: any) {
      const s: VisionStatus = { camera_available: false, error: e?.message || 'Gateway offline' };
      setStatus(s);
      onStatus?.(s);
    }
  }, [onStatus]);

  useEffect(() => {
    loadStatus();
    const id = setInterval(loadStatus, STATUS_INTERVAL_MS);
    return () => clearInterval(id);
  }, [loadStatus]);

  useEffect(() => {
    if (status?.camera_available !== true) {
      setUri(null);
      return;
    }
    let alive = true;
    const tick = () => {
      if (!alive) return;
      setUri(visionFrameUrl());
    };
    tick();
    const id = setInterval(tick, FRAME_INTERVAL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [status?.camera_available]);

  const offline = status?.camera_available === false;
  const waiting = status === null;

  return (
    <View style={styles.card}>
      <View style={styles.frame}>
        {waiting && (
          <View style={styles.center}>
            <ActivityIndicator color={PALETTE.primary} />
            <Text style={styles.centerText}>Connecting to camera…</Text>
          </View>
        )}

        {!waiting && offline && (
          <View style={styles.center}>
            <MaterialCommunityIcons name="video-off-outline" size={34} color={PALETTE.textFaint} />
            <Text style={styles.offlineTitle}>Camera offline</Text>
            <Text style={styles.centerText}>
              {status?.error && status.error !== 'Camera unavailable. Check CAMERA_SOURCE / USB connection.'
                ? status.error
                : 'No video device on the gateway. Connect the USB camera or set CAMERA_SOURCE.'}
            </Text>
            {!!status?.camera_source && (
              <Text style={styles.source}>source: {status.camera_source}</Text>
            )}
          </View>
        )}

        {!waiting && !offline && uri && !frameError && (
          <Image
            key="feed"
            source={{ uri }}
            style={StyleSheet.absoluteFill}
            resizeMode="contain"
            onLoad={(e: any) => {
              errorStreak.current = 0;
              setFrameError(false);
              setLastFrameAt(Date.now());
              const s = e?.nativeEvent?.source;
              if (s?.width && s?.height) setSize({ w: s.width, h: s.height });
            }}
            onError={() => {
              errorStreak.current += 1;
              if (errorStreak.current >= 2) setFrameError(true);
            }}
          />
        )}

        {!waiting && !offline && uri && frameError && (
          <View style={styles.center}>
            <MaterialCommunityIcons name="image-off-outline" size={32} color={PALETTE.textFaint} />
            <Text style={styles.offlineTitle}>Waiting for frames</Text>
            <Text style={styles.centerText}>The camera is reported online but frames are not arriving.</Text>
          </View>
        )}

        {!offline && !waiting && (
          <View style={styles.liveBadge}>
            <View style={styles.liveDot} />
            <Text style={styles.liveText}>LIVE</Text>
          </View>
        )}
      </View>

      <View style={styles.meta}>
        <View style={styles.metaItem}>
          <MaterialCommunityIcons name="aspect-ratio" size={13} color={PALETTE.textFaint} />
          <Text style={styles.metaText}>{size ? `${size.w}×${size.h}` : 'JPEG'}</Text>
        </View>
        <View style={styles.metaItem}>
          <MaterialCommunityIcons name="sync" size={13} color={PALETTE.textFaint} />
          <Text style={styles.metaText}>2 fps poll</Text>
        </View>
        <View style={styles.metaItem}>
          <View
            style={[
              styles.metaDot,
              { backgroundColor: offline ? PALETTE.danger : lastFrameAt ? PALETTE.success : PALETTE.warning },
            ]}
          />
          <Text style={styles.metaText} numberOfLines={1}>
            {offline
              ? 'no signal'
              : lastFrameAt
                ? `frame ${nowMs ? Math.max(1, Math.round((nowMs - lastFrameAt) / 1000)) : 1}s ago`
                : 'waiting'}
          </Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    borderRadius: RADIUS.lg,
    overflow: 'hidden',
  },
  frame: {
    width: '100%',
    aspectRatio: 16 / 9,
    backgroundColor: '#070B10',
    justifyContent: 'center',
  },
  center: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: SPACING.xl,
    gap: 6,
  },
  centerText: {
    fontFamily: FONT.sans,
    fontSize: 12,
    lineHeight: 17,
    color: PALETTE.textFaint,
    textAlign: 'center',
    maxWidth: 300,
  },
  offlineTitle: {
    fontFamily: FONT.sansSemiBold,
    fontSize: 14,
    color: PALETTE.textMuted,
  },
  source: { fontFamily: FONT.mono, fontSize: 10, color: PALETTE.textFaint },
  liveBadge: {
    position: 'absolute',
    top: 10,
    left: 10,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(7,11,16,0.82)',
    borderWidth: 1,
    borderColor: 'rgba(255,107,107,0.4)',
    borderRadius: RADIUS.pill,
    paddingHorizontal: 9,
    paddingVertical: 4,
  },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: PALETTE.danger, marginRight: 6 },
  liveText: { fontFamily: FONT.sansSemiBold, fontSize: 9, letterSpacing: 1.2, color: PALETTE.text },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: SPACING.md,
    paddingVertical: 9,
    borderTopWidth: 1,
    borderTopColor: PALETTE.outlineSoft,
    gap: 8,
  },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 5, flexShrink: 1 },
  metaText: { fontFamily: FONT.mono, fontSize: 10, color: PALETTE.textMuted },
  metaDot: { width: 5, height: 5, borderRadius: 3 },
});
