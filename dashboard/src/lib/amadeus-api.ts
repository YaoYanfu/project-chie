const AMADEUS_API_BASE = (import.meta.env.VITE_AMADEUS_API_URL || 'http://127.0.0.1:8765').replace(/\/$/, '')

export interface RemoteStatus {
  configured: boolean
  online: boolean
  reason?: string
  service?: string
  version?: string
  bot_nickname?: string
  started_at?: string
  uptime_seconds?: number
}

export interface IdentityStatus {
  configured: boolean
  mapped: boolean
  person_id?: string
  display_name?: string
  source_platform?: string
  reason?: string
}

export interface TtsStatus {
  state: 'stopped' | 'starting' | 'running' | string
  running: boolean
  managed: boolean
  pid?: number | null
  host?: string
  port?: number
}

export interface AmadeusStatus {
  remote: RemoteStatus
  identity: IdentityStatus
  local: {
    amadeus: { online: boolean }
    tts: TtsStatus
  }
}

export interface AmadeusEvent {
  id: string
  created_at: string
  source: string
  event_type: string
  summary: string
  status: 'info' | 'warning' | 'error' | string
  metadata: Record<string, unknown>
}

export interface AmadeusCommand {
  id: string
  created_at: string
  action: string
  status: 'accepted' | 'pending_approval' | 'approved' | 'rejected' | string
  payload: Record<string, unknown>
  decided_at?: string | null
  decision_reason: string
}

export interface RemoteConfig {
  remote_base_url: string
  remote_token_configured: boolean
  owner_person_id: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${AMADEUS_API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(payload?.detail || `Amadeus 请求失败 (${response.status})`)
  }
  return response.json() as Promise<T>
}

export function getAmadeusWebSocketUrl(): string {
  return `${AMADEUS_API_BASE.replace(/^http/, 'ws')}/api/chat/ws`
}

export const amadeusApi = {
  health: () => request<{ status: string }>('/health'),
  status: () => request<AmadeusStatus>('/api/status'),
  events: () => request<{ events: AmadeusEvent[]; total: number }>('/api/events?limit=80'),
  deleteEvent: (eventId: string) => request<{ success: boolean }>(`/api/events/${eventId}`, { method: 'DELETE' }),
  commands: () => request<{ commands: AmadeusCommand[]; total: number }>('/api/commands?limit=80'),
  decideCommand: (commandId: string, approved: boolean, reason = '') =>
    request<AmadeusCommand>(`/api/commands/${commandId}/decision`, {
      method: 'POST',
      body: JSON.stringify({ approved, reason }),
    }),
  ttsStart: () => request<TtsStatus>('/api/services/tts/start', { method: 'POST' }),
  ttsStop: () => request<TtsStatus>('/api/services/tts/stop', { method: 'POST' }),
  remoteConfig: () => request<RemoteConfig>('/api/config/remote'),
  updateRemoteConfig: (payload: { remote_base_url: string; remote_token: string; owner_person_id: string }) =>
    request<RemoteConfig & { success: boolean }>('/api/config/remote', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
}
