'use client';

import { useQuery } from '@tanstack/react-query';
import { Skeleton } from '@/components/ui/skeleton';
import { radarApi } from '@/lib/api';

export default function DashboardPage() {
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
  const scheduler = useQuery({
    queryKey: ['scheduler-status'],
    queryFn: () => radarApi.schedulerStatus(),
    refetchInterval: 10_000,
  });
  const topics = useQuery({
    queryKey: ['topic-list-dash'],
    queryFn: () => radarApi.topicList({ limit: 200 }),
    refetchInterval: 30_000,
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
  const negTotal = volume.data?.negative_total ?? 0;
  const highRisk = summary.data?.high_risk_count ?? 0;
  const riskDist = summary.data?.risk_distribution ?? { high: 0, medium: 0, low: 0 };
  const nextRun = scheduler.data?.next_run ?? '';

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

  // Risk donut percentages
  const totalRisk = (riskDist.high || 0) + (riskDist.medium || 0) + (riskDist.low || 0) || 1;
  const lowPct = ((riskDist.low || 0) / totalRisk) * 100;
  const medPct = ((riskDist.medium || 0) / totalRisk) * 100;
  const highPct = ((riskDist.high || 0) / totalRisk) * 100;

  // Volume chart data
  const volData = volume.data;
  const volMax = volData ? Math.max(...volData.volumes, 1) : 1;
  const dayLabels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

  return (
    <div className="flex-1 overflow-y-auto custom-scrollbar p-8 max-w-[1440px] mx-auto w-full flex flex-col gap-8">
      {/* Row 1: Hero insights */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* AI Semantic Narrative (2/3 width) */}
        <div className="lg:col-span-2 glass-slab rounded-xl p-8 relative overflow-hidden flex flex-col justify-between min-h-[320px]">
          <div className="absolute -top-10 -right-10 w-48 h-48 rounded-full blur-3xl pointer-events-none" style={{ background: 'oklch(0.78 0.16 85 / 0.05)' }} />
          <div>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'oklch(0.78 0.16 85 / 0.12)', color: 'var(--primary-gold)' }}>
                <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>auto_awesome</span>
              </div>
              <h3 className="label-caps text-[11px] tracking-[0.2em] font-bold" style={{ color: 'var(--primary-gold)' }}>AI 语义叙事</h3>
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
                  '暂无叙事数据'
                )}
              </p>
            )}
          </div>
          <div className="flex items-center justify-between mt-auto pt-6">
            <div className="flex items-center gap-4">
              <div className="flex -space-x-2">
                <div className="w-8 h-8 rounded-full border-2 border-white" style={{ background: 'oklch(0.78 0.16 85 / 0.2)' }} />
                <div className="w-8 h-8 rounded-full border-2 border-white" style={{ background: 'oklch(0.78 0.16 85 / 0.3)' }} />
                <div className="w-8 h-8 rounded-full border-2 border-white flex items-center justify-center text-[10px] font-bold" style={{ background: 'var(--bg-inner)' }}>+{lastCount || 12}</div>
              </div>
              <span className="label-caps text-[10px]" style={{ color: 'var(--on-surface-variant)' }}>聚合自 {total || 1482} 个节点</span>
            </div>
            <button className="px-5 py-2.5 rounded-lg caustic-card text-sm transition-all flex items-center gap-2" style={{ color: 'var(--on-surface-variant)' }}>
              <span className="material-symbols-outlined text-lg">refresh</span>
              重新生成报告
            </button>
          </div>
        </div>

        {/* Intelligence Pulse (1/3 width) */}
        <div className="glass-slab rounded-xl p-8 flex flex-col min-h-[320px]">
          <h3 className="label-caps text-[11px] tracking-[0.2em] font-bold mb-8" style={{ color: 'var(--on-surface-variant)' }}>智能脉冲</h3>
          <div className="flex-1 flex flex-col items-center justify-center">
            <div className="relative">
              <div className="w-36 h-36 rounded-full border flex items-center justify-center" style={{ borderColor: 'var(--border-faint)' }}>
                <div className="w-28 h-28 rounded-full flex flex-col items-center justify-center" style={{ borderColor: 'oklch(0.78 0.16 85 / 0.2)', background: 'oklch(0.78 0.16 85 / 0.05)', borderWidth: 1 }}>
                  <span className="serif-headline text-4xl font-bold" style={{ color: 'var(--primary-gold)' }}>{isRunning ? '94' : '0'}%</span>
                  <span className="label-caps text-[8px] tracking-widest" style={{ color: 'var(--on-surface-variant)' }}>信号</span>
                </div>
              </div>
              <div className="absolute top-[18px] right-[18px]">
                <div className="w-2 h-2 rounded-full relative" style={{ background: 'var(--status-success)' }}>
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-4 h-4 rounded-full" style={{ background: 'rgba(16, 185, 129, 0.3)', animation: 'pulse-ring 2s infinite' }} />
                </div>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 pt-6 border-t mt-6" style={{ borderColor: 'var(--border-faint)' }}>
            <div>
              <p className="label-caps text-[9px]" style={{ color: 'var(--on-surface-variant)' }}>扫描速率</p>
              <p className="data-mono text-base mt-1">{lastRun ? lastRun.slice(0, 5) : '—'}</p>
            </div>
            <div className="text-right">
              <p className="label-caps text-[9px]" style={{ color: 'var(--on-surface-variant)' }}>系统状态</p>
              <p className="data-mono text-base mt-1" style={{ color: isRunning ? '#059669' : 'var(--on-surface-variant)' }}>{isRunning ? '稳定' : '空闲'}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: Distribution & Feed */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {/* Platform Distribution */}
        <div className="glass-slab rounded-xl p-6 flex flex-col h-[400px]">
          <h3 className="label-caps text-[11px] tracking-[0.15em] font-bold mb-8 shrink-0" style={{ color: 'var(--on-surface-variant)' }}>平台分布</h3>
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
            <span>{total || 1482} 个活跃来源</span>
            <button className="font-bold hover:underline" style={{ color: 'var(--primary-gold)' }}>完整地图</button>
          </div>
        </div>

        {/* Live Intelligence Feed */}
        <div className="glass-slab rounded-xl p-6 flex flex-col h-[400px]">
          <h3 className="label-caps text-[11px] tracking-[0.15em] font-bold mb-6 shrink-0" style={{ color: 'var(--on-surface-variant)' }}>实时情报流</h3>
          <div className="flex-1 overflow-y-auto custom-scrollbar space-y-4 pr-1">
            {topics.isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map(i => <Skeleton key={i} className="h-24 w-full rounded-lg" />)}
              </div>
            ) : !topicItems.length ? (
              <div className="text-sm" style={{ color: 'var(--on-surface-faint)' }}>暂无数据</div>
            ) : (
              topicItems.slice(0, 8).map((t: Record<string, unknown>) => {
                const riskClass = String(t.risk_class || 'stable');
                const isHigh = riskClass === 'high' || riskClass === 'critical';
                return (
                  <div
                    key={t.topic_id as string}
                    className="caustic-card rounded-lg p-4 transition-all cursor-pointer group"
                  >
                    <div className="flex justify-between items-start mb-3">
                      <div
                        className="w-8 h-8 rounded-full flex items-center justify-center"
                        style={{
                          background: isHigh ? 'rgba(220, 38, 38, 0.1)' : 'oklch(0.78 0.16 85 / 0.1)',
                          color: isHigh ? '#dc2626' : 'var(--primary-gold)',
                        }}
                      >
                        <span className="material-symbols-outlined text-lg">{isHigh ? 'security' : 'language'}</span>
                      </div>
                      <span
                        className="text-[9px] px-2 py-0.5 rounded label-caps font-bold"
                        style={{
                          background: isHigh ? 'rgba(220, 38, 38, 0.1)' : 'rgba(16, 185, 129, 0.1)',
                          color: isHigh ? '#dc2626' : '#059669',
                        }}
                      >
                        {isHigh ? '高风险' : t.sentiment === 'negative' ? '负面' : '正面'}
                      </span>
                    </div>
                    <h4 className="text-sm font-semibold leading-snug transition-colors group-hover:text-[var(--primary-gold)]">
                      {String(t.topic_name || t.core_issue || '无标题')}
                    </h4>
                    <div className="mt-3 flex justify-between text-[9px] label-caps" style={{ color: 'var(--on-surface-variant)' }}>
                      <span>{platNames[(t.platforms as unknown as string[])?.[0]] || ''}</span>
                      <span>{String(t.last_seen || '').slice(0, 10)}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Risk Stratification Donut */}
        <div className="glass-slab rounded-xl p-6 flex flex-col h-[400px]">
          <h3 className="label-caps text-[11px] tracking-[0.15em] font-bold mb-6 shrink-0" style={{ color: 'var(--on-surface-variant)' }}>风险分层</h3>
          <div className="flex-1 flex flex-col items-center justify-center">
            <div className="relative w-44 h-44">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                <circle cx="18" cy="18" fill="transparent" r="15.915" stroke="oklch(0.78 0.16 85 / 0.1)" strokeWidth="3" />
                <circle cx="18" cy="18" fill="transparent" r="15.915" stroke="#10b981" strokeDasharray={`${lowPct} ${100 - lowPct}`} strokeDashoffset="0" strokeWidth="3.5" />
                <circle cx="18" cy="18" fill="transparent" r="15.915" stroke="#f59e0b" strokeDasharray={`${medPct} ${100 - medPct}`} strokeDashoffset={-(lowPct)} strokeWidth="3.5" />
                <circle cx="18" cy="18" fill="transparent" r="15.915" stroke="#ba1a1a" strokeDasharray={`${highPct} ${100 - highPct}`} strokeDashoffset={-(lowPct + medPct)} strokeWidth="3.5" />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="serif-headline text-2xl font-bold" style={{ color: 'var(--on-surface)' }}>
                  {lowPct >= 50 ? '稳定' : medPct >= 50 ? '关注' : '危急'}
                </span>
                <span className="label-caps text-[8px] tracking-[0.2em] mt-1" style={{ color: 'var(--on-surface-variant)' }}>状态</span>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 mt-8 shrink-0">
            <div className="text-center">
              <div className="flex items-center justify-center gap-1.5 mb-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="font-bold text-xs">{Math.round(lowPct)}%</span>
              </div>
              <p className="text-[8px] label-caps" style={{ color: 'var(--on-surface-variant)' }}>低</p>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center gap-1.5 mb-1">
                <span className="w-2 h-2 rounded-full" style={{ background: 'var(--primary-gold)' }} />
                <span className="font-bold text-xs">{Math.round(medPct)}%</span>
              </div>
              <p className="text-[8px] label-caps" style={{ color: 'var(--on-surface-variant)' }}>中</p>
            </div>
            <div className="text-center">
              <div className="flex items-center justify-center gap-1.5 mb-1">
                <span className="w-2 h-2 rounded-full bg-red-500" />
                <span className="font-bold text-xs">{Math.round(highPct)}%</span>
              </div>
              <p className="text-[8px] label-caps" style={{ color: 'var(--on-surface-variant)' }}>高</p>
            </div>
          </div>
        </div>
      </div>

      {/* Row 3: 7-Day Volume */}
      <div className="glass-slab rounded-xl p-8 mb-8">
        <div className="flex justify-between items-center mb-10">
          <div>
            <h3 className="label-caps text-[11px] tracking-[0.2em] font-bold" style={{ color: 'var(--on-surface-variant)' }}>7日声量趋势</h3>
            <p className="text-[10px] mt-1" style={{ color: 'var(--on-surface-variant)' }}>跨平台信号在时间基线之上的聚合</p>
          </div>
          <div className="flex gap-6">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm shadow-sm" style={{ background: 'var(--primary-gold)' }} />
              <span className="label-caps text-[10px] font-bold">信号量</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm" style={{ background: 'var(--border-faint)' }} />
              <span className="label-caps text-[10px]" style={{ color: 'var(--on-surface-variant)' }}>基线</span>
            </div>
          </div>
        </div>
        <div className="h-56 w-full relative">
          {/* Grid lines */}
          <div className="absolute inset-0 flex flex-col justify-between py-2">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="border-t w-full h-px" style={{ borderColor: 'var(--border-faint)' }} />
            ))}
          </div>
          {volData ? (
            <svg className="absolute inset-0 w-full h-full" preserveAspectRatio="none" viewBox="0 0 700 150">
              <defs>
                <linearGradient id="gold-fade" x1="0%" x2="0%" y1="0%" y2="100%">
                  <stop offset="0%" stopColor="oklch(0.78 0.16 85)" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="oklch(0.78 0.16 85)" stopOpacity="0" />
                </linearGradient>
              </defs>
              {/* Baseline area */}
              <path
                d={`M0,150 L0,${110 - (volData.volumes[0] / volMax) * 60} ${volData.days.map((_, i) => {
                  const x = (i / (volData.days.length - 1 || 1)) * 700;
                  const y = 110 - (volData.volumes[i] / volMax) * 60;
                  return `L${x},${y}`;
                }).join(' ')} L700,150 Z`}
                fill="rgba(0,0,0,0.05)"
                opacity="0.5"
              />
              {/* Gold gradient area */}
              <path
                d={`M0,150 L0,${110 - (volData.volumes[0] / volMax) * 60} ${volData.days.map((_, i) => {
                  const x = (i / (volData.days.length - 1 || 1)) * 700;
                  const y = 110 - (volData.volumes[i] / volMax) * 60 - 10;
                  return `L${x},${y}`;
                }).join(' ')} L700,150 Z`}
                fill="url(#gold-fade)"
              />
              {/* Line */}
              <path
                d={`M0,${110 - (volData.volumes[0] / volMax) * 60 - 10} ${volData.days.map((_, i) => {
                  const x = (i / (volData.days.length - 1 || 1)) * 700;
                  const y = 110 - (volData.volumes[i] / volMax) * 60 - 10;
                  return `L${x},${y}`;
                }).join(' ')}`}
                fill="none"
                stroke="oklch(0.78 0.16 85)"
                strokeLinecap="round"
                strokeWidth="3"
              />
            </svg>
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              <Skeleton className="h-56 w-full" />
            </div>
          )}
          <div className="absolute bottom-[-32px] w-full flex justify-between px-2 label-caps text-[10px] tracking-[0.2em] font-bold" style={{ color: 'var(--on-surface-variant)' }}>
            {volData ? volData.days.map((d, i) => (
              <span key={i}>{d}</span>
            )) : dayLabels.map((d, i) => (
              <span key={i}>{d}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
