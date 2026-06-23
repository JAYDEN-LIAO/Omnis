/**
 * MediaRadar Web 前端 API 客户端
 * 后端路径: mediaradar.jaydennn.xyz (生产) / localhost:8008 (开发)
 */
// 空字符串 = 同源请求（走 Next.js rewrite），不匹配时 fallback 到 localhost
const BASE = process.env.NEXT_PUBLIC_API_BASE || '';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', 'X-API-Key': API_KEY };
  let token: string | null = null;

  if (typeof window !== 'undefined') {
    token = localStorage.getItem('mediaradar_token');
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE}${path}`, {
    headers: { ...headers, ...(options?.headers as Record<string, string> | undefined) },
    ...options,
  });

  if (res.status === 401 && token && typeof window !== 'undefined' && !path.startsWith('/api/auth/')) {
    localStorage.removeItem('mediaradar_token');
    // 区分游客 vs 普通用户的提示
    const isGuest = (() => { try { const p = JSON.parse(atob(token.split('.')[1])); return p?.role === 'guest'; } catch { return false; } })();
    window.location.href = '/login';
    throw new Error(isGuest ? '游客会话已过期，请重新访问' : '登录已过期，请重新登录');
  }
  if (res.status === 403) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.msg || '权限不足');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.msg || `HTTP ${res.status}`);
  }
  const json = await res.json();
  // 自动拆解 { code, data, msg } → data，保持前端简洁
  if (json && typeof json === 'object' && 'code' in json && 'data' in json) {
    return json.data as T;
  }
  return json as T;
}

// ============================================================
// Types
// ============================================================

export interface AgentMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AgentSession {
  session_id: string;
  title: string;
  created_at?: string;
}

export interface TopicListItem {
  topic_id: string;
  keyword: string;
  topic_name: string;
  cluster_summary?: string;
  risk_level: number;
  risk_class: string;
  risk_text: string;
  sentiment: string;
  evolution_signal: string;
  core_issue: string;
  report?: string;
  platforms: string[];
  post_count: number;
  last_seen: string;
  is_processed: number;
}

export interface SystemSettings {
  keywords: string[];
  inactive_keywords: string[];
  platforms: string[];
  push_summary: boolean;
  push_time: string;
  alert_negative: boolean;
  monitor_frequency: number;
  start_time: string;
}

export interface PushConfig {
  enabled: boolean;
  risk_min_level: number;
  // email
  smtp_host?: string;
  smtp_port?: number;
  smtp_user?: string;
  smtp_password?: string;
  smtp_use_tls?: boolean;
  from_addr?: string;
  to_addrs?: string[];
  // webhook
  webhook_url?: string;
}

export interface LLMConfigItem {
  label: string;
  role: string;
  default_model: string;
  effective_base_url: string;
  effective_model: string;
  base_url: string;
  model: string;
  has_key: boolean;
  api_key_masked: string;
  uses_default: boolean;
}

export interface VolumeStats {
  days: string[];
  volumes: number[];
  negative_volumes: number[];
  keywords_volumes?: Record<string, number[]>;
  total: number;
  negative_total: number;
}

// ============================================================
// Radar API
// ============================================================

export const radarApi = {
  status: () => request<{ is_running?: boolean; status_text?: string; last_run_time?: string; last_new_count?: number }>('/api/radar_status'),

  todaySummary: () =>
    request<{ sentiment?: string; summary?: string; keyword?: string; high_risk_count?: number; risk_distribution?: { high: number; medium: number; low: number }; suppressed_count?: number }>(
      '/api/today_summary',
    ),

  volumeStats: (keyword?: string) =>
    request<VolumeStats>(
      `/api/volume_stats${keyword ? `?keyword=${encodeURIComponent(keyword)}` : ''}`
    ),

  topicList: (params?: { keyword?: string; platform?: string; sentiment?: string; is_processed?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.keyword) qs.set('keyword', params.keyword);
    if (params?.platform) qs.set('platform', params.platform);
    if (params?.sentiment) qs.set('sentiment', params.sentiment);
    if (params?.is_processed !== undefined) qs.set('is_processed', String(params.is_processed));
    if (params?.limit) qs.set('limit', String(params.limit));
    return request<TopicListItem[]>(`/api/topic_list?${qs.toString()}`);
  },

  startTask: () =>
    request<{ msg: string }>('/api/start_task', { method: 'POST', body: '{}' }),

  settings: () => request<SystemSettings>('/api/settings'),

  saveSettings: (v: SystemSettings) =>
    request<{ msg: string }>('/api/settings', {
      method: 'POST',
      body: JSON.stringify(v),
    }),

  schedulerStart: () =>
    request<{ msg: string }>('/api/scheduler/start', { method: 'POST', body: '{}' }),

  schedulerStop: () =>
    request<{ msg: string }>('/api/scheduler/stop', { method: 'POST', body: '{}' }),

  schedulerStatus: () =>
    request<{ active?: boolean; next_run?: string; interval_hours?: number; scan_in_progress?: boolean }>('/api/scheduler/status'),
};

// ============================================================
// Agent API
// ============================================================

export const agentApi = {
  memory: () =>
    request<{ data: { sessions: AgentSession[]; total: number } }>('/api/agent/memory'),

  deleteSession: (sessionId: string) =>
    request<{ success: boolean; deleted: number }>(`/api/agent/memory/${sessionId}`, { method: 'DELETE' }),

  messages: (sessionId: string) =>
    request<{ data: { messages: { role: string; content: string; created_at: string }[]; total: number } }>(
      `/api/agent/memory/${sessionId}/messages`,
    ),
};

// ============================================================
// Push Config API
// ============================================================

export const pushApi = {
  configs: () => request<Record<string, PushConfig>>('/api/push/configs'),

  save: (channel: string, config: PushConfig) =>
    request<{ msg: string }>(`/api/push/config/${channel}`, {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  test: (channel: string) =>
    request<{ msg: string }>('/api/push/test', {
      method: 'POST',
      body: JSON.stringify({ channel }),
    }),
};

// ============================================================
// LLM Config API
// ============================================================

// ============================================================
// Auth API
// ============================================================

export const authApi = {
  guestLogin: () =>
    request<{ token: string; user: { role: string } }>('/api/auth/guest-login', {
      method: 'POST', body: '{}',
    }),

  register: (email: string, password: string, nickname?: string) =>
    request<{ token: string; user: { user_id: string; nickname: string; role: string } }>(
      '/api/auth/register',
      { method: 'POST', body: JSON.stringify({ email, password, nickname }) },
    ),

  login: (email: string, password: string) =>
    request<{ token: string; user: { user_id: string; nickname: string; role: string } }>(
      '/api/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) },
    ),

  me: () => request<{ user_id: string; nickname: string; email?: string; role: string; oauth_provider?: string }>('/api/auth/me'),

  updateProfile: (nickname: string) =>
    request<{ msg: string }>('/api/auth/profile', {
      method: 'PUT',
      body: JSON.stringify({ nickname }),
    }),
};

export const llmApi = {
  configs: () => request<Record<string, LLMConfigItem>>('/api/llm/configs'),

  save: (agent: string, config: { api_key?: string; base_url?: string; model?: string }) =>
    request<{ msg: string }>(`/api/llm/config/${agent}`, {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  test: (agent: string, config?: { api_key?: string; base_url?: string; model?: string }) =>
    request<{ code: number; msg: string }>(`/api/llm/test/${agent}`, {
      method: 'POST',
      body: JSON.stringify(config || {}),
    }),
};
