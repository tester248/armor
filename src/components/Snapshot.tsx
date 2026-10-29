import React, { useEffect, useState } from 'react';
import { Image, Pressable, StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { snapshotUrl } from '../api';
import { FONT, PALETTE, RADIUS, SPACING } from '../theme';

type Props = {
  path?: string | null;
  caption?: string;
  /** Aspect ratio of the frame. 16/9 keeps phone-camera captures letterboxed, never cropped. */
  aspectRatio?: number;
  onPress?: () => void;
};

/**
 * A stored inspection snapshot. Backend paths can be Windows or POSIX, so the
 * URL is normalised by snapshotUrl(). Snapshot is always `contain` — cropping a
 * safety image would hide the violation it exists to prove.
 */
export default function Snapshot({ path, caption, aspectRatio = 16 / 9, onPress }: Props) {
  const uri = snapshotUrl(path);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setFailed(false);
    setLoaded(false);
  }, [uri]);

  const body = (
    <View style={[styles.frame, { aspectRatio }]}>
      {!uri && (
        <View style={styles.center}>
          <MaterialCommunityIcons name="image-off-outline" size={26} color={PALETTE.textFaint} />
          <Text style={styles.hint}>No snapshot stored for this event</Text>
        </View>
      )}

      {!!uri && !failed && (
        <Image
          source={{ uri }}
          style={StyleSheet.absoluteFill}
          resizeMode="contain"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
      )}

      {!!uri && !failed && !loaded && (
        <View style={styles.center}>
          <MaterialCommunityIcons name="image-outline" size={26} color={PALETTE.textFaint} />
          <Text style={styles.hint}>Loading snapshot…</Text>
        </View>
      )}

      {!!uri && failed && (
        <View style={styles.center}>
          <MaterialCommunityIcons name="file-image-remove-outline" size={26} color={PALETTE.warning} />
          <Text style={styles.hint}>Snapshot file is missing on the gateway</Text>
        </View>
      )}
    </View>
  );

  return (
    <View style={styles.wrap}>
      {onPress && !!uri ? (
        <Pressable onPress={onPress} accessibilityRole="imagebutton" accessibilityLabel="Open snapshot">
          {body}
        </Pressable>
      ) : (
        body
      )}
      {!!caption && (
        <View style={styles.captionRow}>
          <MaterialCommunityIcons name="camera-outline" size={13} color={PALETTE.textFaint} />
          <Text style={styles.caption} numberOfLines={1}>
            {caption}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderRadius: RADIUS.md,
    borderWidth: 1,
    borderColor: PALETTE.outlineSoft,
    backgroundColor: '#070B10',
    overflow: 'hidden',
  },
  frame: { width: '100%', justifyContent: 'center' },
  center: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingHorizontal: SPACING.lg,
  },
  hint: {
    fontFamily: FONT.sans,
    fontSize: 12,
    color: PALETTE.textFaint,
    textAlign: 'center',
  },
  captionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: SPACING.md,
    paddingVertical: 7,
    borderTopWidth: 1,
    borderTopColor: PALETTE.outlineSoft,
  },
  caption: { fontFamily: FONT.mono, fontSize: 10, color: PALETTE.textFaint, flex: 1 },
});
