const API_BASE = process.env.EXPO_PUBLIC_ARMOR_API_URL || 'http://10.0.2.2:8000';

async function req(path: string, init?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  health: () => req('/api/v1/health'),
  status: (deviceId: string) => req(`/api/v1/status/${deviceId}`),
  telemetry: (deviceId: string, limit = 60) => req(`/api/v1/telemetry/${deviceId}?limit=${limit}`),
  incidents: (deviceId?: string) => req(`/api/v1/incidents${deviceId ? `?device_id=${deviceId}` : ''}`),
  workers: () => req('/api/v1/workers'),
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
};

export const DEFAULT_DEVICE_ID = 'machino_node_01';