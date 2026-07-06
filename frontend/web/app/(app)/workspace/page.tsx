'use client';

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { Skeleton } from '@/components/ui/skeleton';
import { workflowApi, type WorkflowItem } from '@/lib/api';
import { toast } from 'sonner';

const PRESET_META: Record<string, { icon: string; color: string; label: string }> = {
  deep_analyze_topic: {
    icon: 'travel_explore',
    color: '#6366f1',
    label: '深度分析',
  },
  scan_and_alert: {
    icon: 'notifications_active',
    color: '#dc2626',
    label: '扫描预警',
  },
  quick_guide: {
    icon: 'map',
    color: '#10b981',
    label: '攻略规划',
  },
  briefing_digest: {
    icon: 'summarize',
    color: '#f59e0b',
    label: '简报摘要',
  },
};

const PRESET_DEFAULTS: Record<string, { keyword: string; platforms: string }> = {
  deep_analyze_topic: { keyword: '', platforms: '微博,小红书' },
  scan_and_alert: { keyword: '', platforms: '全部' },
  quick_guide: { keyword: '', platforms: '小红书,大众点评' },
  briefing_digest: { keyword: '', platforms: '全部' },
};

export default function WorkspacePage() {
  const router = useRouter();
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => { document.title = '工作台 — Omnis'; }, []);

  const { data, isLoading } = useQuery({
    queryKey: ['workflows'],
    queryFn: () => workflowApi.list(),
    refetchInterval: 15_000,
  });

  const presets = data?.presets ?? [];
  const userWorkflows = data?.user_workflows ?? [];
  const recentRuns = userWorkflows.filter((w) => w.source === 'auto_template').slice(0, 5);
  const myWorkflows = userWorkflows.filter((w) => w.source === 'user');

  const handleRunPreset = (name: string) => {
    const meta = PRESET_META[name];
    const label = meta?.label || name;
    // 跳转到信息助手，带预设指令
    router.push(`/agent?q=/run ${name}`);
    toast.success(`正在启动${label}...`);
  };

  return (
    <div className="flex-1 overflow-y-auto custom-scrollbar p-8 max-w-[1400px] mx-auto w-full flex flex-col gap-8">
      {/* ── 预设工作流 ── */}
      <section>
        <h2 className="label-caps text-[11px] tracking-[0.2em] font-bold mb-6" style={{ color: 'var(--primary-gold)' }}>
          预设工作流
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
          {isLoading
            ? Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="glass-slab rounded-xl p-6" style={{ height: 200 }}>
                  <Skeleton className="h-full w-full" />
                </div>
              ))
            : presets.map((wf) => {
                const meta = PRESET_META[wf.name] || { icon: 'settings', color: 'var(--primary-gold)', label: wf.name };
                return (
                  <button
                    key={wf.id}
                    onClick={() => handleRunPreset(wf.name)}
                    className="glass-slab rounded-xl p-6 text-left transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 group cursor-pointer"
                    style={{ borderColor: 'var(--border-faint)' }}
                  >
                    <div
                      className="w-12 h-12 rounded-xl flex items-center justify-center mb-5"
                      style={{ background: `${meta.color}15` }}
                    >
                      <span className="material-symbols-outlined text-2xl" style={{ color: meta.color }}>
                        {meta.icon}
                      </span>
                    </div>
                    <h3 className="serif-headline text-lg mb-2" style={{ color: 'var(--on-surface)' }}>
                      {meta.label}
                    </h3>
                    <p className="text-sm leading-relaxed" style={{ color: 'var(--on-surface-variant)' }}>
                      {wf.description}
                    </p>
                    <div className="mt-4 flex items-center gap-1 text-xs font-bold" style={{ color: 'var(--primary-gold)', opacity: 0, transition: 'opacity 0.2s' }}>
                      <span className="group-hover:opacity-100" style={{ opacity: 1 }}>
                        立即运行
                      </span>
                      <span className="material-symbols-outlined text-sm">arrow_forward</span>
                    </div>
                  </button>
                );
              })}
        </div>
      </section>

      {/* ── 最近运行 ── */}
      <section>
        <h2 className="label-caps text-[11px] tracking-[0.2em] font-bold mb-6" style={{ color: 'var(--primary-gold)' }}>
          最近运行
        </h2>
        <div className="glass-slab rounded-xl overflow-hidden">
          {isLoading ? (
            <div className="p-6 space-y-4">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16 w-full rounded-lg" />
              ))}
            </div>
          ) : recentRuns.length === 0 ? (
            <div className="p-8 text-center text-sm" style={{ color: 'var(--on-surface-faint)' }}>
              暂无运行记录 — 在信息助手中与 Agent 对话后，常用步骤将自动保存为模板
            </div>
          ) : (
            <div className="divide-y divide-[color:var(--border-faint)]">
              {recentRuns.map((wf) => (
                <div
                  key={wf.id}
                  className="flex items-center justify-between px-6 py-4 transition-colors hover:bg-[oklch(0_0_0/0.02)]"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'oklch(0.78 0.16 85 / 0.1)' }}>
                      <span className="material-symbols-outlined text-lg" style={{ color: 'var(--primary-gold)' }}>
                        history
                      </span>
                    </div>
                    <div>
                      <p className="text-sm font-semibold" style={{ color: 'var(--on-surface)' }}>{wf.name}</p>
                      <p className="text-xs mt-0.5" style={{ color: 'var(--on-surface-variant)' }}>
                        {wf.last_run ? new Date(wf.last_run).toLocaleString('zh-CN') : '—'} · 已运行 {wf.run_count ?? 0} 次
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleRunPreset(wf.name)}
                    className="caustic-card px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5"
                    style={{ color: 'var(--on-surface-variant)' }}
                  >
                    <span className="material-symbols-outlined text-sm">replay</span>
                    再次运行
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* ── 我的工作流 ── */}
      <section>
        <div className="flex items-center justify-between mb-6">
          <h2 className="label-caps text-[11px] tracking-[0.2em] font-bold" style={{ color: 'var(--primary-gold)' }}>
            我的工作流
          </h2>
          <button
            className="label-caps text-[11px] font-bold flex items-center gap-1.5 px-4 py-2 rounded-lg transition-all"
            style={{ color: 'var(--primary-gold)', background: 'oklch(0.78 0.16 85 / 0.08)' }}
            onClick={() => router.push('/agent')}
          >
            <span className="material-symbols-outlined text-sm">add</span>
            新建工作流
          </button>
        </div>
        <div className="glass-slab rounded-xl overflow-hidden">
          {myWorkflows.length === 0 ? (
            <div className="p-8 text-center text-sm" style={{ color: 'var(--on-surface-faint)' }}>
              暂无自定义工作流 — 在信息助手中发起任务后，可另存为定时工作流
            </div>
          ) : (
            <div className="divide-y divide-[color:var(--border-faint)]">
              {myWorkflows.map((wf) => (
                <div
                  key={wf.id}
                  className="flex items-center justify-between px-6 py-4 transition-colors hover:bg-[oklch(0_0_0/0.02)]"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: wf.enabled ? 'oklch(0.95 0.03 155)' : 'var(--bg-inner)' }}>
                      <span className="material-symbols-outlined text-lg" style={{ color: wf.enabled ? '#059669' : 'var(--on-surface-faint)' }}>
                        {wf.enabled ? 'schedule' : 'schedule'}
                      </span>
                    </div>
                    <div>
                      <p className="text-sm font-semibold" style={{ color: 'var(--on-surface)' }}>{wf.name}</p>
                      <p className="text-xs mt-0.5" style={{ color: 'var(--on-surface-variant)' }}>
                        {wf.schedule_cron ? `定时: ${wf.schedule_cron}` : '手动触发'}
                        {wf.last_run && ` · 上次: ${new Date(wf.last_run).toLocaleString('zh-CN')}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${wf.enabled ? 'bg-green-500' : 'bg-gray-300'}`}
                    />
                    <span className="text-xs label-caps" style={{ color: 'var(--on-surface-variant)' }}>
                      {wf.enabled ? '启用' : '停用'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
