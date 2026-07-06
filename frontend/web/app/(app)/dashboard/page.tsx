'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Skeleton } from '@/components/ui/skeleton';
import { radarApi, workflowApi } from '@/lib/api';

export default function DashboardPage() {
  useEffect(() => { document.title = '数据看板 — Omnis'; }, []);
  const status = useQuery({
    queryKey: ['radar-status'],
    queryFn: () => radarApi.status(),
    refetchInterval: 3000,
  });
  const summary = useQuery({
    queryKey: ['today-summary'],
    queryFn: () => radarApi.todaySummary(),
    refetchInterval: 10_000,
  });
  const volume = useQuery({
    queryKey: ['volume-stats'],
    queryFn: () => radarApi.volumeStats(),
    refetchInterval: 30_000,
  });
  const topics = useQuery({
    queryKey: ['topic-list-dash'],
    queryFn: () => radarApi.topicList({ limit: 200 }),
    refetchInterval: 30_000,
  });
  const workflows = useQuery({
    queryKey: ['workflows-dash'],
    queryFn: () => workflowApi.list(),
    refetchInterval: 15_000,
  });

  if (status.error && summary.error && volume.error) {
    return (
      <div className="flex flex-col items-center gap-3 pt-20 text-sm" style={{ color: 'var(--on-surface-variant)' }}>
        <p>无法连接后端服务</p>
        <button onClick={() => { status.refetch(); summary.refetch(); volume.refetch(); }} className="underline" style={{ color: 'var(--primary-gold)' }}>重试</button>
      </div>
    );
  }

  const isRunning = status.data?.is_running ?? false;
  const lastRun = status.data?.last_run_time ?? '';
  const lastCount = status.data?.last_new_count ?? 0;
  const total = volume.data?.total ?? 0;
  const presets = workflows.data?.presets ?? [];
  const userWfs = workflows.data?.user_workflows ?? [];

  // Platform distribution
  const topicItems: Array<Record<string, unknown>> = (topics.data ?? []) as unknown as Array<Record<string, unknown>>;
  const platformMap: Record<string, number> = {};
  topicItems.forEach((t: Record<string, unknown>) => {
    const plats = (t.platforms as unknown as string[]) ?? [];
    plats.forEach((p: string) => { platformMap[p] = (platformMap[p] || 0) + 1; });
  });
  const platNames: Record<string, string> = { wb: '微博', xhs: '小红书', bili: 'B站', zhihu: '知乎', dy: '抖音', ks: '快手', tieba: '贴吧' };
  const platformEntries = Object.entries(platformMap).sort((a, b) => b[1] - a[1]);
  const maxCount = platformEntries[0]?.[1] || 1;

  // Volume chart data
  const volData = volume.data;
  const volMax = volData ? Math.max(...volData.volumes, 1) : 1;
  const dayLabels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

  return (
    <div className="flex-1 overflow-y-auto custom-scrollbar p-8 max-w-[1440px] mx-auto w-full flex flex-col gap-8">
      {/* Row 1: System narrative + Agent status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* AI 系统概览 (2/3) */}
        <div className="lg:col-span-2 glass-slab rounded-xl p-8 relative overflow-hidden flex flex-col justify-between min-h-[320px]">
          <div className="absolute -top-10 -right-10 w-48 h-48 rounded-full blur-3xl pointer-events-none" style={{ background: 'oklch(0.78 0.16 85 / 0.05)' }} />
          <div>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'oklch(0.78 0.16 85 / 0.12)', color: 'var(--primary-gold)' }}>
                <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>auto_awesome</span>
              </div>
              <h3 className="label-caps text-[11px] tracking-[0.2em] font-bold" style={{ color: 'var(--primary-gold)' }}>系统概览</h3>
            </div>
            {summary.isLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-4/5" />
                <Skeleton className="h-6 w-3/5" />
              </div>
            ) : (
              <p className="serif-headline text-2xl leading-snug max-w-2xl" style={{ color: 'var(--on-surface)' }}>
                {summary.data?.summary ? (
                  <>
                    <span className="font-bold italic" style={{ color: 'var(--primary-gold)' }}>{summary.data.summary.split('。')[0]}。</span>
                    {summary.data.summary.includes('。') && (
                      <span> {summary.data.summary.split('。').slice(1).join('。')}</span>
                    )}
                  </>
                ) : (
                  '暂无数据 — 请先在信息助手中发起分析任务'
                )}
              </p>
            )}
          </div>
          <div className="flex items-center justify-between mt-auto pt-6">
            <div className="flex items-center gap-4">
              <div className="flex -space-x-2">
                <div className="w-8 h-8 rounded-full border-2 border-white" style={{ background: 'oklch(0.78 0.16 85 / 0.2)' }} />
                <div className="w-8 h-8 rounded-full border-2 border-white" style={{ background: 'oklch(0.78 0.16 85 / 0.3)' }} />
                <div className="w-8 h-8 rounded-full border-2 border-white flex items-center justify-center text-[10px] font-bold" style={{ background: 'var(--bg-inner)' }}>{lastCount || 0}</div>
              </div>
              <span className="label-caps text-[10px]" style={{ color: 'var(--on-surface-variant)' }}>
                已采集 {total || 0} 条数据 · {presets.length} 个预设工作流
              </span>
            </div>
          </div>
        </div>

        {/* Agent 状态 (1/3) */}
        <div className="glass-slab rounded-xl p-8 flex flex-col min-h-[320px]">
          <h3 className="label-caps text-[11px] tracking-[0.2em] font-bold mb-8" style={{ color: 'var(--on-surface-variant)' }}>Agent 状态</h3>
          <div className="flex-1 flex flex-col items-center justify-center">
            <div className="relative">
              <div className="w-36 h-36 rounded-full border flex items-center justify-center" style={{ borderColor: 'var(--border-faint)' }}>
                <div className="w-28 h-28 rounded-full flex flex-col items-center justify-center" style={{ borderColor: 'oklch(0.78 0.16 85 / 0.2)', background: 'oklch(0.78 0.16 85 / 0.05)', borderWidth: 1 }}>
                  <span className="serif-headline text-4xl font-bold" style={{ color: 'var(--primary-gold)' }}>{isRunning ? '94' : '0'}%</span>
                  <span className="label-caps text-[8px] tracking-widest" style={{ color: 'var(--on-surface-variant)' }}>活跃度</span>
                </div>
              </div>
              <div className="absolute top-[18px] right-[18px]">
                <div className="w-2 h-2 rounded-full relative" style={{ background: isRunning ? '#059669' : 'var(--on-surface-faint)' }}>
                  {isRunning && (
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-4 h-4 rounded-full" style={{ background: 'rgba(16, 185, 129, 0.3)', animation: 'pulse-ring 2s infinite' }} />
                  )}
                </div>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 pt-6 border-t mt-6" style={{ borderColor: 'var(--border-faint)' }}>
            <div>
              <p className="label-caps text-[9px]" style={{ color: 'var(--on-surface-variant)' }}>工作流</p>
              <p className="data-mono text-base mt-1">{userWfs.length} 个</p>
            </div>
            <div className="text-right">
              <p className="label-caps text-[9px]" style={{ color: 'var(--on-surface-variant)' }}>状态</p>
              <p className="data-mono text-base mt-1" style={{ color: isRunning ? '#059669' : 'var(--on-surface-variant)' }}>{isRunning ? '稳定' : '空闲'}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: Data source distribution + Activity feed */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {/* 数据来源分布 */}
        <div className="glass-slab rounded-xl p-6 flex flex-col h-[400px]">
          <h3 className="label-caps text-[11px] tracking-[0.15em] font-bold mb-8 shrink-0" style={{ color: 'var(--on-surface-variant)' }}>数据来源</h3>
          <div className="flex-1 space-y-7 overflow-y-auto custom-scrollbar pr-1">
            {topics.isLoading ? (
              <div className="space-y-6">
                {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-8 w-full" />)}
              </div>
            ) : platformEntries.length === 0 ? (
              <div className="text-sm" style={{ color: 'var(--on-surface-faint)' }}>暂无数据</div>
            ) : (
              platformEntries.slice(0, 4).map(([key, count]) => {
                const pct = (count / maxCount) * 100;
                return (
                  <div key={key} className="space-y-2.5">
                    <div className="flex justify-between label-caps text-[10px]" style={{ color: 'var(--on-surface-variant)' }}>
                      <span>{platNames[key] || key}</span>
                      <span className="font-bold" style={{ color: 'var(--on-surface)' }}>{Math.round(pct)}%</span>
                    </div>
                    <div className="h-1 rounded-full overflow-hidden" style={{ background: 'oklch(0.78 0.16 85 / 0.1)' }}>
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--primary-gold)' }} />
                    </div>
                  </div>
                );
              })
            )}
          </div>
          <div className="mt-auto pt-6 border-t flex items-center justify-between label-caps text-[10px] shrink-0" style={{ borderColor: 'var(--border-faint)', color: 'var(--on-surface-variant)' }}>
            <span>{total || 0} 条采集数据</span>
          </div>
        </div>

        {/* 最近活动 */}
        <div className="glass-slab rounded-xl p-6 flex flex-col h-[400px]">
          <h3 className="label-caps text-[11px] tracking-[0.15em] font-bold mb-6 shrink-0" style={{ color: 'var(--on-surface-variant)' }}>最近活动</h3>
          <div className="flex-1 overflow-y-auto custom-scrollbar space-y-4 pr-1">
            {topics.isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map(i => <Skeleton key={i} className="h-24 w-full rounded-lg" />)}
              </div>
            ) : !topicItems.length ? (
              <div className="text-sm" style={{ color: 'var(--on-surface-faint)' }}>暂无活动记录</div>
            ) : (
              topicItems.slice(0, 8).map((t: Record<string, unknown>) => (
                <div
                  key={t.topic_id as string}
                  className="caustic-card rounded-lg p-4 transition-all cursor-pointer group"
                >
                  <div className="flex justify-between items-start mb-3">
                    <div className="w-8 h-8 rounded-full flex items-center justify-center" style={{ background: 'oklch(0.78 0.16 85 / 0.1)', color: 'var(--primary-gold)' }}>
                      <span className="material-symbols-outlined text-lg">language</span>
                    </div>
                    <span className="text-[9px] px-2 py-0.5 rounded label-caps font-bold" style={{ background: 'oklch(0.78 0.16 85 / 0.1)', color: 'var(--primary-gold)' }}>
                      {String((t.platforms as unknown as string[])?.[0] || '')}
                    </span>
                  </div>
                  <h4 className="text-sm font-semibold leading-snug transition-colors group-hover:text-[var(--primary-gold)]">
                    {String(t.topic_name || t.core_issue || '无标题')}
                  </h4>
                  <div className="mt-3 flex justify-between text-[9px] label-caps" style={{ color: 'var(--on-surface-variant)' }}>
                    <span>{String(t.keyword || '')}</span>
                    <span>{String(t.last_seen || '').slice(0, 10)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* 快速统计 */}
        <div className="glass-slab rounded-xl p-6 flex flex-col h-[400px]">
          <h3 className="label-caps text-[11px] tracking-[0.15em] font-bold mb-6 shrink-0" style={{ color: 'var(--on-surface-variant)' }}>快速统计</h3>
          <div className="flex-1 flex flex-col justify-center gap-8">
            <div className="text-center">
              <p className="serif-headline text-5xl font-bold" style={{ color: 'var(--primary-gold)' }}>{total}</p>
              <p className="label-caps text-[10px] mt-2" style={{ color: 'var(--on-surface-variant)' }}>累计采集数据</p>
            </div>
            <div className="grid grid-cols-2 gap-6">
              <div className="text-center">
                <p className="serif-headline text-2xl font-bold" style={{ color: 'var(--on-surface)' }}>{presets.length}</p>
                <p className="label-caps text-[9px] mt-1" style={{ color: 'var(--on-surface-variant)' }}>预设工作流</p>
              </div>
              <div className="text-center">
                <p className="serif-headline text-2xl font-bold" style={{ color: 'var(--on-surface)' }}>{userWfs.length}</p>
                <p className="label-caps text-[9px] mt-1" style={{ color: 'var(--on-surface-variant)' }}>运行/自定义</p>
              </div>
            </div>
            {volData && (
              <div className="pt-4 border-t" style={{ borderColor: 'var(--border-faint)' }}>
                <p className="label-caps text-[9px] mb-3" style={{ color: 'var(--on-surface-variant)' }}>近7日趋势</p>
                <div className="flex items-end gap-1.5 h-20">
                  {volData.volumes.map((v: number, i: number) => {
                    const h = (v / volMax) * 68;
                    return (
                      <div key={i} className="flex-1 flex flex-col items-center gap-1">
                        <div
                          className="w-full rounded-sm transition-all"
                          style={{ height: Math.max(h, 2), background: 'var(--primary-gold)', opacity: 0.6 + (h / 68) * 0.4 }}
                        />
                        <span className="text-[7px] label-caps" style={{ color: 'var(--on-surface-variant)' }}>{volData.days[i].slice(0, 2)}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
