const API_BASE = process.env.EXPO_PUBLIC_ARMOR_API_URL || 'http://10.0.2.2:8000';

async function req(path: string, init?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
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
  interlock: (command: 'LOCKOUT' | 'RESET', deviceId: string, issuedBy = 'mobile_app') =>
    req(`/api/v1/interlock?device_id=${deviceId}`, {
      method: 'POST',
      body: JSON.stringify({ command, source: 'MOBILE_APP', reason: 'Manual override from mobile', issued_by: issuedBy }),
    }),
  resetIncident: (incidentId: string, deviceId: string, resetBy = 'mobile_app') =>
    req(`/api/v1/interlock/reset/${incidentId}?device_id=${deviceId}&reset_by=${resetBy}`, { method: 'POST' }),
  breach: (deviceId: string, workerId: string, badgeMac: string) =>
    req('/api/v1/breach', {
      method: 'POST',
      body: JSON.stringify({ device_id: deviceId, worker_id: workerId, badge_mac: badgeMac, distance_est_m: 1.2 }),
    }),

  // ── Incidents ────────────────────────────────────────────────────────────
  incidents: (deviceId?: string) =>
    req(`/api/v1/incidents${deviceId ? `?device_id=${deviceId}` : ''}`),
  incident: (incidentId: string) => req(`/api/v1/incidents/${incidentId}`),

  // ── Workers ──────────────────────────────────────────────────────────────
  workers: () => req('/api/v1/workers'),
  registerWorker: (badgeMac: string, workerId: string, workerName?: string, department?: string) =>
    req('/api/v1/workers', {
      method: 'POST',
      body: JSON.stringify({ badge_mac: badgeMac, worker_id: workerId, worker_name: workerName, department: department || 'Fabrication', active: true }),
    }),
  deactivateWorker: (badgeMac: string) => req(`/api/v1/workers/${badgeMac}`, { method: 'DELETE' }),

  // ── Vision ───────────────────────────────────────────────────────────────
  visionInspectStart: (workerId: string, deviceId: string) =>
    req(`/api/v1/vision/inspect/start?worker_id=${workerId}&device_id=${deviceId}`, { method: 'POST' }),
  visionInspectStatus: () => req('/api/v1/vision/inspect/status'),
  visionInspectSync: (workerId: string, deviceId: string) =>
    req(`/api/v1/vision/inspect?worker_id=${workerId}&device_id=${deviceId}`, { method: 'POST' }),

  // ── Calibration & ML ─────────────────────────────────────────────────────
  calibrate: (deviceId: string, contamination = 0.05) =>
    req(`/api/v1/calibrate?device_id=${deviceId}&contamination=${contamination}`, { method: 'POST' }),
  model: (deviceId: string) => req(`/api/v1/model/${deviceId}`),
  anomalies: (deviceId: string, limit = 20) =>
    req(`/api/v1/anomalies?device_id=${deviceId}&limit=${limit}`),

  // ── Debug ────────────────────────────────────────────────────────────────
  debugMqtt: (limit = 10) => req(`/api/v1/debug/mqtt?limit=${limit}`),
};

export const DEFAULT_DEVICE_ID = 'machino_node_01';

// WebSocket URL for live telemetry push
export const WS_BASE = (process.env.EXPO_PUBLIC_ARMOR_API_URL || 'http://10.0.2.2:8000')
  .replace('http://', 'ws://')
  .replace('https://', 'wss://');
