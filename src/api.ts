const rawBase = process.env.EXPO_PUBLIC_ARMOR_API_URL || 'http://10.24.103.187:8000';
export const API_BASE = rawBase.replace(/\/+$/, '');

const REQUEST_TIMEOUT_MS = 7000;

export class ApiError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function req<T = any>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    });
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const body = await res.json();
        if (body?.detail) detail = String(body.detail);
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(detail, res.status);
    }
    return (await res.json()) as T;
  } catch (err: any) {
    if (err?.name === 'AbortError') throw new ApiError('Backend did not respond in time', 0);
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/** Build a cache-busted URL for one JPEG frame from the gateway. */
export function visionFrameUrl(): string {
  return `${API_BASE}/api/v1/vision/frame?t=${Date.now()}`;
}

/** Turn a backend snapshot path (POSIX or Windows) into a servable URL. */
export function snapshotUrl(path?: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  const filename = path.split(/[\\/]/).pop();
  if (!filename) return null;
  return `${API_BASE}/api/v1/vision/snapshot/${encodeURIComponent(filename)}`;
}

export const api = {
  // ── System ────────────────────────────────────────────────────────────────
  health: () => req('/api/v1/health'),

  // ── Status & Telemetry ───────────────────────────────────────────────────
  status: (deviceId: string) => req(`/api/v1/status/${deviceId}`),
  telemetry: (deviceId: string, limit = 60) =>
    req(`/api/v1/telemetry/${deviceId}?limit=${limit}`),
  devices: () => req('/api/v1/devices'),

  // ── Safety ───────────────────────────────────────────────────────────────
  interlock: (
    command: 'LOCKOUT' | 'RESET' | 'START' | 'STOP',
    deviceId: string,
    issuedBy = 'mobile_app',
  ) =>
    req(`/api/v1/interlock?device_id=${deviceId}`, {
      method: 'POST',
      body: JSON.stringify({
        command,
        source: 'MOBILE_APP',
        reason:
          command === 'START'
            ? 'Operator started motor from mobile app'
            : command === 'STOP'
              ? 'Operator stopped motor from mobile app'
              : 'Manual override from mobile',
        issued_by: issuedBy,
      }),
    }),
  resetIncident: (incidentId: string, deviceId: string, resetBy = 'mobile_app') =>
    req(`/api/v1/interlock/reset/${incidentId}?device_id=${deviceId}&reset_by=${resetBy}`, {
      method: 'POST',
    }),
  breach: (deviceId: string, workerId: string, badgeMac: string) =>
    req('/api/v1/breach', {
      method: 'POST',
      body: JSON.stringify({
        device_id: deviceId,
        worker_id: workerId,
        badge_mac: badgeMac,
        distance_est_m: 1.2,
      }),
    }),
  /** Bench mode is published over MQTT so the ESP32 suppresses proximity trips. */
  benchMode: (enabled: boolean, deviceId: string) =>
    req(`/api/v1/bench?enabled=${enabled}&device_id=${deviceId}`, { method: 'POST' }),

  // ── Incidents ────────────────────────────────────────────────────────────
  incidents: (deviceId?: string) =>
    req(`/api/v1/incidents${deviceId ? `?device_id=${deviceId}` : ''}`),
  incident: (incidentId: string) => req(`/api/v1/incidents/${incidentId}`),

  // ── Workers ──────────────────────────────────────────────────────────────
  workers: () => req('/api/v1/workers'),
  registerWorker: (badgeMac: string, workerId: string, workerName?: string, department?: string) =>
    req('/api/v1/workers', {
      method: 'POST',
      body: JSON.stringify({
        badge_mac: badgeMac,
        worker_id: workerId,
        worker_name: workerName,
        department: department || 'Fabrication',
        active: true,
      }),
    }),
  deactivateWorker: (badgeMac: string) => req(`/api/v1/workers/${badgeMac}`, { method: 'DELETE' }),

  // ── Vision ───────────────────────────────────────────────────────────────
  visionInspectStart: (workerId: string, deviceId: string) =>
    req(`/api/v1/vision/inspect/start?worker_id=${workerId}&device_id=${deviceId}`, {
      method: 'POST',
    }),
  visionInspectStatus: () => req('/api/v1/vision/inspect/status'),
  visionInspectSync: (workerId: string, deviceId: string) =>
    req(`/api/v1/vision/inspect?worker_id=${workerId}&device_id=${deviceId}`, { method: 'POST' }),
  visionStatus: () => req('/api/v1/vision/status'),

  // ── Calibration & ML ─────────────────────────────────────────────────────
  /** Per-modality fault attribution from the multi-modal IsolationForest. */
  decomposition: (deviceId: string) =>
    req(`/api/v1/telemetry/anomaly/decomposition/${deviceId}`),
  advisory: (deviceId: string) =>
    req(`/api/v1/telemetry/prediction/${deviceId}`),
  calibrate: (deviceId: string, contamination = 0.05) =>
    req(`/api/v1/calibrate?device_id=${deviceId}&contamination=${contamination}`, {
      method: 'POST',
    }),
  model: (deviceId: string) => req(`/api/v1/model/${deviceId}`),
  anomalies: (deviceId: string, limit = 20) =>
    req(`/api/v1/anomalies?device_id=${deviceId}&limit=${limit}`),

  // ── Debug ────────────────────────────────────────────────────────────────
  debugMqtt: (limit = 10) => req(`/api/v1/debug/mqtt?limit=${limit}`),
};

export const DEFAULT_DEVICE_ID =
  process.env.EXPO_PUBLIC_ARMOR_DEVICE_ID || 'machino_node_01';

// WebSocket URL for live telemetry push
export const WS_BASE = API_BASE.replace('http://', 'ws://').replace('https://', 'wss://');
