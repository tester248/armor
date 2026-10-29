import { useCallback, useEffect, useRef, useState } from 'react';
import { api, DEFAULT_DEVICE_ID } from '../api';

/**
 * Shared 2s poll of machine status + recent telemetry.
 * Pauses while the screen is unfocused so we do not hammer the gateway.
 */
export function useMachineStatus(pollMs = 2000, sampleLimit = 60, active = true) {
  const [status, setStatus] = useState<any>(null);
  const [telemetry, setTelemetry] = useState<any[]>([]);
  const [decomposition, setDecomposition] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const mounted = useRef(true);

  const load = useCallback(async () => {
    try {
      const [s, t, d] = await Promise.all([
        api.status(DEFAULT_DEVICE_ID),
        api.telemetry(DEFAULT_DEVICE_ID, sampleLimit),
        api.decomposition(DEFAULT_DEVICE_ID).catch(() => null),
      ]);
      if (!mounted.current) return;
      setStatus(s);
      setTelemetry(Array.isArray(t?.samples) ? t.samples : []);
      if (d) setDecomposition(d);
      setError(null);
      setUpdatedAt(Date.now());
    } catch (e: any) {
      if (!mounted.current) return;
      setError(e?.message || 'Gateway unreachable');
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [sampleLimit]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!active) return;
    load();
    const id = setInterval(load, pollMs);
    return () => clearInterval(id);
  }, [load, pollMs, active]);

  return { status, telemetry, decomposition, error, loading, updatedAt, refresh: load };
}
