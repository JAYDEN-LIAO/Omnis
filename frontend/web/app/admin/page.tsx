'use client';

import { useEffect, useState } from 'react';
import { Users, Gauge, Activity, AlertCircle, Loader2 } from 'lucide-react';

interface AdminStats {
  total_users: number;
  total_subscriptions: number;
  active_subscriptions: number;
  today_topics: number;
  scheduler_active: boolean;
}

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('mediaradar_token');
}

export default function AdminHomePage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8008';
    const token = getToken();
    fetch(`${apiBase}/api/admin/stats`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.json())
      .then(j => { if (j?.data) setStats(j.data); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">管理总览</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Omnis v2.2 · 多用户 SaaS · 订阅平台
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="glass-slab rounded-xl p-5">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium" style={{ color: 'var(--on-surface-variant)' }}>注册用户</span>
            <Users className="h-4 w-4 opacity-40" style={{ color: 'var(--on-surface-variant)' }} />
          </div>
          <div className="text-2xl font-semibold" style={{ color: 'var(--on-surface)' }}>{stats?.total_users ?? '—'}</div>
          <p className="mt-1 text-xs" style={{ color: 'var(--on-surface-variant)' }}>
            <a href="/admin/users" style={{ color: 'var(--primary-gold)' }} className="hover:underline">查看用户管理</a>
          </p>
        </div>

        <div className="glass-slab rounded-xl p-5">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium" style={{ color: 'var(--on-surface-variant)' }}>活跃订阅</span>
            <Activity className="h-4 w-4 opacity-40" style={{ color: 'var(--on-surface-variant)' }} />
          </div>
          <div className="text-2xl font-semibold" style={{ color: 'var(--on-surface)' }}>{stats?.active_subscriptions ?? '—'}</div>
          <p className="mt-1 text-xs" style={{ color: 'var(--on-surface-variant)' }}>
            总共 {stats?.total_subscriptions ?? 0} 条 · 跨用户汇总
          </p>
        </div>

        <div className="glass-slab rounded-xl p-5">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium" style={{ color: 'var(--on-surface-variant)' }}>今日话题</span>
            <Gauge className="h-4 w-4 opacity-40" style={{ color: 'var(--on-surface-variant)' }} />
          </div>
          <div className="text-2xl font-semibold" style={{ color: 'var(--on-surface)' }}>{stats?.today_topics ?? '—'}</div>
          <p className="mt-1 text-xs" style={{ color: 'var(--on-surface-variant)' }}>过去 24 小时活跃话题</p>
        </div>

        <div className="glass-slab rounded-xl p-5">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium" style={{ color: 'var(--on-surface-variant)' }}>调度器</span>
            <AlertCircle className="h-4 w-4 opacity-40" style={{ color: 'var(--on-surface-variant)' }} />
          </div>
          <div className="text-2xl font-semibold" style={{ color: stats?.scheduler_active ? 'var(--status-success)' : 'var(--on-surface-variant)' }}>
            {stats?.scheduler_active ? '运行中' : '已停止'}
          </div>
          <p className="mt-1 text-xs" style={{ color: 'var(--on-surface-variant)' }}>
            {stats?.scheduler_active ? '定时扫描已启用' : '需手动启动调度器'}
          </p>
        </div>
      </div>

      <div className="glass-slab rounded-xl p-5">
        <h3 className="serif-headline text-sm font-semibold mb-3" style={{ color: 'var(--on-surface)' }}>快捷入口</h3>
        <div className="space-y-2 text-sm" style={{ color: 'var(--on-surface-variant)' }}>
          <p>· <a href="/admin/users" style={{ color: 'var(--primary-gold)' }} className="hover:underline">用户管理</a> — 搜索、禁用用户</p>
          <p>· <a href="/admin/quota" style={{ color: 'var(--primary-gold)' }} className="hover:underline">配额调整</a> — 查看和修改用户配额</p>
          <p>· <a href="/dashboard" style={{ color: 'var(--primary-gold)' }} className="hover:underline">全局仪表盘</a> — 系统级数据视图</p>
          <p>· <a href="/settings/system" style={{ color: 'var(--primary-gold)' }} className="hover:underline">系统设置</a> — 关键词 / 平台 / 推送配置</p>
        </div>
      </div>
    </div>
  );
}
