/**
 * 前端 token 管理
 */
const TOKEN_KEY = 'mediaradar_token';
const ROLE_COOKIE = 'mediaradar_role';
const TOKEN_COOKIE = 'mediaradar_token_cookie';  // 给 middleware 读

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  // 同时写 cookie（middleware 才能读）
  if (typeof document !== 'undefined') {
    document.cookie = `${TOKEN_COOKIE}=${encodeURIComponent(token)}; path=/; max-age=86400; SameSite=Lax`;
  }
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  if (typeof document !== 'undefined') {
    document.cookie = `${TOKEN_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
    document.cookie = `${ROLE_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
  }
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

/**
 * 设置/清除角色 cookie（供 middleware 读）
 */
export function setRoleCookie(role: string) {
  if (typeof document === 'undefined') return;
  document.cookie = `${ROLE_COOKIE}=${encodeURIComponent(role)}; path=/; max-age=86400; SameSite=Lax`;
}

/**
 * 完整登录后写入：token + role 双 cookie
 * 供登录/注册/OAuth 回调页面调用
 */
export function persistAuth(token: string, role: string) {
  setToken(token);
  setRoleCookie(role);
}

/**
 * 解析 JWT payload（前端不解签，仅读明文 payload）
 */
function _decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    let payload = parts[1];
    // 补 base64 padding
    const pad = 4 - (payload.length % 4);
    if (pad !== 4) payload += '='.repeat(pad);
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}

/**
 * 判断当前用户是否为游客（前端解码 JWT 中的 role）
 */
export function isGuest(): boolean {
  const token = getToken();
  if (!token) return false;
  const payload = _decodeJwtPayload(token);
  return payload?.role === 'guest';
}

/**
 * 获取游客会话剩余时间（毫秒），返回 0 表示已过期或非游客
 */
export function getGuestRemainingTime(): number {
  const token = getToken();
  if (!token) return 0;
  const payload = _decodeJwtPayload(token);
  if (payload?.role !== 'guest') return 0;
  const exp = (payload.exp as number) * 1000;
  const remaining = exp - Date.now();
  return Math.max(0, remaining);
}

/**
 * 游客剩余时间格式化为 mm:ss
 */
export function formatGuestTime(ms: number): string {
  if (ms <= 0) return '0:00';
  const totalSec = Math.floor(ms / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}:${sec.toString().padStart(2, '0')}`;
}
