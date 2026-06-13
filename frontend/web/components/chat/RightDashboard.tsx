'use client';

/**
 * IntelligenceLive —— AI 助手右侧看板（gold 主题）。
 *
 * 模块：
 *   1. Risk Radar — SVG gauge（雷达状态）
 *   2. Hot Clusters — 热门话题/关键词
 *   3. Neural Engine — 调度器 + 快捷操作
 */
import { useQuery } from '@tanstack/react-query';
import { Skeleton } from '@/components/ui/skeleton';
import { radarApi } from '@/lib/api';

interface Props {
  onQuickAction?: (text: string) => void;
}

export function RightDashboard({ onQuickAction }: Props) {
  const statusQ = useQuery({
    queryKey: ['radar-status'],
    queryFn: () => radarApi.status(),
    refetchInterval: 10_000,
  });

  const todayQ = useQuery({
    queryKey: ['today-summary'],
    queryFn: () => radarApi.todaySummary(),
    refetchInterval: 60_000,
  });

  const riskIndex = statusQ.data?.is_running ? 0.18 : 0.0;
  const signalPct = statusQ.data?.is_running ? 75 : 0;

  return (
    <>
      {/* Header */}
      <div className="p-6 border-b flex items-center justify-between" style={{ borderColor: 'rgba(0,0,0,0.05)' }}>
        <h3 className="serif-headline text-lg" style={{ color: 'var(--on-surface)' }}>智能实况</h3>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[9px] label-caps font-bold tracking-widest" style={{ color: '#059669' }}>脉冲活跃</span>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto scrollbar-hide p-6 space-y-8">
        {/* Risk Radar */}
        <section>
          <div className="flex justify-between items-center mb-4">
            <span className="text-[10px] label-caps font-bold tracking-widest" style={{ color: 'var(--on-surface-variant)' }}>风险雷达</span>
            <span className="text-[10px] label-caps" style={{ color: 'var(--on-surface-variant)', opacity: 0.5 }}>全球运营</span>
          </div>
          {statusQ.isLoading ? (
            <Skeleton className="w-32 h-32 mx-auto rounded-full" />
          ) : (
            <div className="relative w-32 h-32 mx-auto">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                <circle cx="18" cy="18" fill="none" r="16" stroke="rgba(0,0,0,0.03)" strokeWidth="4" />
                <circle
                  className="gold-glow-ambient"
                  cx="18" cy="18" fill="none" r="16"
                  stroke="oklch(0.78 0.16 85)"
                  strokeDasharray={`${signalPct}, 100`}
                  strokeLinecap="round"
                  strokeWidth="4"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-lg font-bold data-mono">{riskIndex.toFixed(2)}</span>
                <span className="text-[8px] label-caps tracking-widest" style={{ opacity: 0.4 }}>指数</span>
              </div>
            </div>
          )}
        </section>

        {/* Hot Clusters */}
        <section>
          <h4 className="text-[10px] label-caps font-bold tracking-widest mb-4" style={{ color: 'var(--on-surface-variant)' }}>热门聚类</h4>
          {todayQ.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-20 w-full rounded-lg" />
              <Skeleton className="h-20 w-full rounded-lg" />
            </div>
          ) : todayQ.data?.keyword ? (
            <div className="space-y-3">
              <div className="p-3 rounded-lg border border-white/10 transition-all cursor-pointer hover:scale-[1.01] group" style={{ background: 'rgba(255,255,255,0.2)' }}>
                <div className="flex justify-between items-start mb-1">
                  <span className="text-xs font-bold transition-colors group-hover:text-[var(--primary-gold)]" style={{ color: 'var(--on-surface)' }}>
                    {todayQ.data.keyword}
                  </span>
                  <span className="text-[9px] data-mono" style={{ color: 'var(--primary-gold)' }}>+{todayQ.data.high_risk_count || 0}%</span>
                </div>
                {todayQ.data.summary && (
                  <p className="text-[11px] leading-snug" style={{ color: 'var(--on-surface-variant)', opacity: 0.7 }}>
                    {todayQ.data.summary.slice(0, 80)}...
                  </p>
                )}
              </div>
              <div className="p-3 rounded-lg border border-white/10 transition-all cursor-pointer hover:scale-[1.01] group" style={{ background: 'rgba(255,255,255,0.2)' }}>
                <div className="flex justify-between items-start mb-1">
                  <span className="text-xs font-bold transition-colors group-hover:text-[var(--primary-gold)]" style={{ color: 'var(--on-surface)' }}>
                    能源转型
                  </span>
                  <span className="text-[9px] data-mono" style={{ color: 'var(--primary-gold)' }}>+8%</span>
                </div>
                <p className="text-[11px] leading-snug" style={{ color: 'var(--on-surface-variant)', opacity: 0.7 }}>
                  可持续发展报告推动欧盟市场积极情绪。
                </p>
              </div>
            </div>
          ) : (
            <div className="p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.2)' }}>
              <p className="text-xs" style={{ color: 'var(--on-surface-faint)' }}>暂无热点数据</p>
            </div>
          )}
        </section>
      </div>

      {/* Neural Engine footer */}
      <div className="p-6 border-t" style={{ background: 'oklch(0.78 0.16 85 / 0.05)', borderColor: 'rgba(0,0,0,0.05)' }}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-white/50 flex items-center justify-center border border-white/20 shadow-sm">
            <span className="material-symbols-outlined" style={{ color: 'var(--primary-gold)' }}>account_tree</span>
          </div>
          <div>
            <p className="text-xs font-bold" style={{ color: 'var(--on-surface)' }}>神经引擎</p>
            <p className="text-[10px] data-mono" style={{ color: 'var(--on-surface-variant)', opacity: 0.6 }}>
              负载: {statusQ.data?.is_running ? '24.2' : '0'} tflops
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
