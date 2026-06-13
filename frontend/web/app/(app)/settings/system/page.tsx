'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Skeleton } from '@/components/ui/skeleton';
import { useState, useRef, useEffect } from 'react';
import { radarApi, type SystemSettings } from '@/lib/api';
import { toast } from 'sonner';

const schema = z.object({
  keywords: z.array(z.string().min(1)).min(1, '至少 1 个关键词'),
  inactive_keywords: z.array(z.string()),
  platforms: z.array(z.string()).min(1, '至少 1 个平台'),
  push_summary: z.boolean(),
  push_time: z.string().regex(/^\d{2}:\d{2}$/, '格式 HH:MM'),
  alert_negative: z.boolean(),
  monitor_frequency: z.number().min(5).max(1440),
  start_time: z.string().regex(/^\d{2}:\d{2}$/, '格式 HH:MM'),
});

type FormValues = z.infer<typeof schema>;

const allPlatforms = [
  { id: 'wb', name: '微博', icon: 'public' },
  { id: 'xhs', name: '小红书', icon: 'podcasts' },
  { id: 'bili', name: 'B站', icon: 'video_library' },
  { id: 'zhihu', name: '知乎', icon: 'newspaper' },
  { id: 'dy', name: '抖音', icon: 'chat_bubble' },
  { id: 'ks', name: '快手', icon: 'groups' },
  { id: 'tieba', name: '贴吧', icon: 'share' },
  { id: 'other', name: '其他', icon: 'grid_view' },
];

const INPUT_CLASS =
  'w-full px-4 py-3 rounded-lg bg-white/60 border-[0.5px] border-[color:var(--border-faint)] focus:outline-none focus:border-[color:var(--primary-gold)] focus:ring-2 focus:ring-[oklch(0.78_0.16_85/0.2)] transition-all text-sm text-[color:var(--on-surface)] placeholder:text-[color:var(--on-surface-variant)]/40';

export default function SystemSettingsPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['system-settings'],
    queryFn: () => radarApi.settings(),
  });

  const { data: schedStatus } = useQuery({
    queryKey: ['scheduler-status'],
    queryFn: () => radarApi.schedulerStatus(),
    refetchInterval: 15_000,
  });

  const [keywordDraft, setKeywordDraft] = useState('');
  const [inactiveDraft, setInactiveDraft] = useState('');

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    values: data as FormValues | undefined,
  });

  const save = useMutation({
    mutationFn: (v: FormValues) => radarApi.saveSettings(v as SystemSettings),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['system-settings'] });
    },
  });

  // Auto-save: debounce form changes by 1.5s
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const watched = form.watch();
  const freqValue = watched.monitor_frequency ?? 15;
  const keywords = watched.keywords ?? [];
  const inactive = watched.inactive_keywords ?? [];
  const platforms = watched.platforms ?? [];
  const isLoaded = useRef(false);

  useEffect(() => {
    if (!data) return;
    // Skip the first effect run (data just populated the form)
    if (!isLoaded.current) {
      isLoaded.current = true;
      return;
    }
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = setTimeout(() => {
      form.handleSubmit(
        (v) => save.mutate(v),
        () => {}, // onInvalid – no-op to avoid submitting with validation errors
      )();
    }, 1500);
    return () => {
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watched]);

  const schedulerStart = useMutation({
    mutationFn: () => radarApi.schedulerStart(),
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: ['scheduler-status'] });
      qc.setQueryData(['scheduler-status'], (old: any) => ({ ...old, active: true }));
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scheduler-status'] });
      toast.success('调度器已启动');
    },
  });

  const schedulerStop = useMutation({
    mutationFn: () => radarApi.schedulerStop(),
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: ['scheduler-status'] });
      qc.setQueryData(['scheduler-status'], (old: any) => ({ ...old, active: false }));
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scheduler-status'] });
      toast.success('调度器已停止');
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-60 w-full" />
      </div>
    );
  }

  const addKeyword = () => {
    if (!keywordDraft.trim()) return;
    if (keywords.includes(keywordDraft.trim())) {
      toast.warning('关键词已存在');
      return;
    }
    form.setValue('keywords', [...keywords, keywordDraft.trim()], { shouldValidate: true });
    setKeywordDraft('');
  };
  const removeKeyword = (k: string) => form.setValue('keywords', keywords.filter((x) => x !== k), { shouldValidate: true });

  const addInactive = () => {
    if (!inactiveDraft.trim()) return;
    form.setValue('inactive_keywords', [...inactive, inactiveDraft.trim()], { shouldValidate: true });
    setInactiveDraft('');
  };
  const removeInactive = (k: string) => form.setValue('inactive_keywords', inactive.filter((x) => x !== k), { shouldValidate: true });

  const togglePlatform = (id: string) => {
    if (platforms.includes(id)) {
      form.setValue('platforms', platforms.filter((x) => x !== id), { shouldValidate: true });
    } else {
      form.setValue('platforms', [...platforms, id], { shouldValidate: true });
    }
  };

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="grid grid-cols-12 gap-6">
        {/* Card 1: Scheduler Engine */}
        <section className="col-span-12 lg:col-span-4 glass-slab rounded-2xl p-7 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-[oklch(0.78_0.16_85/0.12)] flex items-center justify-center">
                  <span className="material-symbols-outlined text-[color:var(--primary-gold)]" style={{ fontVariationSettings: "'FILL' 1" }}>schedule</span>
                </div>
                <h3 className="serif-headline text-lg font-semibold text-[color:var(--on-surface)]">调度引擎</h3>
              </div>
              <span className={`label-caps text-[9px] px-2 py-1 rounded-full border ${schedStatus?.active ? 'bg-emerald-50 text-emerald-700 border-emerald-100' : 'bg-amber-50 text-amber-700 border-amber-100'}`}>
                {schedStatus?.active ? '运行中' : '已停止'}
              </span>
            </div>
            <p className="text-sm text-[color:var(--on-surface-variant)] leading-relaxed mb-6">
              实时处理节点，用于自动化数据采集、情感分析和话题聚类。
            </p>
            <div className="space-y-2 mb-6">
              <div className="flex justify-between items-center text-xs">
                <span className="label-caps text-[10px] text-[color:var(--on-surface-variant)]/70">扫描间隔</span>
                <span className="data-mono text-[color:var(--on-surface)]">
                  {schedStatus?.interval_hours ? `${schedStatus.interval_hours * 60} 分钟` : '--'}
                </span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="label-caps text-[10px] text-[color:var(--on-surface-variant)]/70">下次运行</span>
                <span className="data-mono text-[color:var(--primary-gold)] font-semibold">
                  {schedStatus?.next_run
                    ? (() => {
                        const remaining = new Date(schedStatus.next_run).getTime() - Date.now();
                        if (remaining <= 0) return '即将执行';
                        const min = Math.floor(remaining / 60000);
                        const sec = Math.floor((remaining % 60000) / 1000);
                        return `${min} 分 ${sec} 秒`;
                      })()
                    : '--'}
                </span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="label-caps text-[10px] text-[color:var(--on-surface-variant)]/70">调度器状态</span>
                <span className="data-mono text-[color:var(--on-surface)]">
                  {schedStatus?.active ? '活跃' : '闲置'}
                </span>
              </div>
            </div>
          </div>
          <div className="flex flex-col gap-3">
            {schedStatus?.active ? (
              <button
                type="button"
                onClick={() => schedulerStop.mutate()}
                disabled={schedulerStop.isPending}
                className="w-full py-3 bg-white/40 border border-[color:var(--border-faint)] text-[color:var(--on-surface)] rounded-xl label-caps text-[11px] font-medium hover:bg-white/60 transition-all disabled:opacity-50"
              >
                {schedulerStop.isPending ? '停止中...' : '停止引擎'}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => schedulerStart.mutate()}
                disabled={schedulerStart.isPending}
                className="w-full py-3 brushed-gold text-[color:var(--on-surface)] rounded-xl label-caps text-[11px] font-bold flex items-center justify-center gap-2 active:scale-[0.98] transition-all disabled:opacity-50"
              >
                <span className="material-symbols-outlined text-lg">play_arrow</span>
                {schedulerStart.isPending ? '启动中...' : '启动引擎'}
              </button>
            )}
          </div>
        </section>

        {/* Card 2: Intelligence Keywords */}
        <section className="col-span-12 lg:col-span-8 glass-slab rounded-2xl p-7">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-[oklch(0.78_0.16_85/0.12)] flex items-center justify-center">
                <span className="material-symbols-outlined text-[color:var(--primary-gold)]" style={{ fontVariationSettings: "'FILL' 1" }}>key</span>
              </div>
              <h3 className="serif-headline text-lg font-semibold text-[color:var(--on-surface)]">监控关键词</h3>
            </div>
            <span className="label-caps text-[10px] text-[color:var(--on-surface-variant)]/60">{keywords.length} 活跃 · {inactive.length} 归档</span>
          </div>

          <div className="flex gap-2 mb-7">
            <div className="flex-1 relative">
              <input
                value={keywordDraft}
                onChange={(e) => setKeywordDraft(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addKeyword())}
                placeholder="添加监控关键词..."
                className={INPUT_CLASS}
                type="text"
              />
            </div>
            <button
              type="button"
              onClick={addKeyword}
              className="w-12 h-12 brushed-gold text-[color:var(--on-surface)] rounded-lg flex items-center justify-center active:scale-[0.98] transition-all"
            >
              <span className="material-symbols-outlined">add</span>
            </button>
          </div>

          <div className="space-y-6">
            <div>
              <p className="label-caps text-[10px] text-[color:var(--on-surface-variant)]/70 mb-3 tracking-[0.15em]">活跃关注</p>
              <div className="flex flex-wrap gap-2">
                {keywords.map((k) => (
                  <span
                    key={k}
                    className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[oklch(0.78_0.16_85/0.15)] text-[color:var(--on-surface)] border-[0.5px] border-[oklch(0.78_0.16_85/0.4)] text-xs font-medium"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-[color:var(--primary-gold)]" />
                    {k}
                    <button type="button" onClick={() => removeKeyword(k)} className="hover:text-red-600 transition-colors ml-1">
                      <span className="material-symbols-outlined text-sm">close</span>
                    </button>
                  </span>
                ))}
                {keywords.length === 0 && (
                  <span className="text-xs text-[color:var(--on-surface-faint)]">暂无</span>
                )}
              </div>
              {form.formState.errors.keywords && (
                <p className="text-xs mt-2 text-[color:var(--status-error)]">{form.formState.errors.keywords.message}</p>
              )}
            </div>
            <div>
              <p className="label-caps text-[10px] text-[color:var(--on-surface-variant)]/70 mb-3 tracking-[0.15em]">已归档</p>
              <div className="flex flex-wrap gap-2">
                {inactive.map((k) => (
                  <span
                    key={k}
                    className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/40 border-[0.5px] border-[color:var(--border-faint)] text-[color:var(--on-surface-variant)] text-xs opacity-60"
                  >
                    {k}
                    <button type="button" onClick={() => removeInactive(k)} className="hover:text-red-600 transition-colors ml-1">
                      <span className="material-symbols-outlined text-sm">close</span>
                    </button>
                  </span>
                ))}
                {inactive.length === 0 && (
                  <span className="text-xs text-[color:var(--on-surface-faint)]">暂无</span>
                )}
              </div>
            </div>
          </div>

          {/* Inactive keyword input */}
          <div className="mt-6 pt-6 border-t border-[color:var(--border-faint)]">
            <p className="label-caps text-[10px] text-[color:var(--on-surface-variant)]/70 mb-2 tracking-[0.15em]">添加归档关键词</p>
            <div className="flex gap-2">
              <input
                value={inactiveDraft}
                onChange={(e) => setInactiveDraft(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addInactive())}
                placeholder="添加归档关键词..."
                className={INPUT_CLASS}
                type="text"
              />
              <button
                type="button"
                onClick={addInactive}
                className="w-12 h-12 bg-white/40 border border-[color:var(--border-faint)] text-[color:var(--on-surface-variant)] rounded-lg flex items-center justify-center active:scale-[0.98] transition-all"
              >
                <span className="material-symbols-outlined">add</span>
              </button>
            </div>
          </div>
        </section>

        {/* Card 3: Target Platforms */}
        <section className="col-span-12 glass-slab rounded-2xl p-7">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-[oklch(0.78_0.16_85/0.12)] flex items-center justify-center">
                <span className="material-symbols-outlined text-[color:var(--primary-gold)]" style={{ fontVariationSettings: "'FILL' 1" }}>hub</span>
              </div>
              <h3 className="serif-headline text-lg font-semibold text-[color:var(--on-surface)]">目标平台</h3>
            </div>
            <span className="label-caps text-[10px] text-[color:var(--on-surface-variant)]/60">{platforms.length} / {allPlatforms.length} 活跃</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
            {allPlatforms.map((p) => {
              const checked = platforms.includes(p.id);
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => togglePlatform(p.id)}
                  className={`p-4 rounded-xl flex flex-col items-center gap-2 transition-all ${
                    checked ? 'platform-active' : 'platform-inactive'
                  }`}
                >
                  <span
                    className="material-symbols-outlined"
                    style={{
                      color: checked ? 'var(--primary-gold)' : 'var(--on-surface-variant)',
                      fontVariationSettings: checked ? "'FILL' 1" : undefined,
                    }}
                  >
                    {p.icon}
                  </span>
                  <span
                    className="label-caps text-[10px] tracking-[0.15em] font-semibold"
                    style={{ color: checked ? 'var(--on-surface)' : 'var(--on-surface-variant)' }}
                  >
                    {p.name}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        {/* Card 4: Operational Parameters */}
        <section className="col-span-12 glass-slab rounded-2xl p-7">
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-[oklch(0.78_0.16_85/0.12)] flex items-center justify-center">
                <span className="material-symbols-outlined text-[color:var(--primary-gold)]" style={{ fontVariationSettings: "'FILL' 1" }}>tune</span>
              </div>
              <h3 className="serif-headline text-lg font-semibold text-[color:var(--on-surface)]">运营参数</h3>
            </div>
            {save.isPending && (
              <span className="label-caps text-[10px] text-[color:var(--primary-gold)]/70 flex items-center gap-1">
                <span className="material-symbols-outlined text-sm animate-spin">sync</span>
                保存中...
              </span>
            )}
          </div>

          <form>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
              {/* Scan Frequency - Range Slider */}
              <div>
                <label className="label-caps text-[10px] text-[color:var(--on-surface-variant)]/70 mb-4 block tracking-[0.15em]">扫描频率</label>
                <div className="mb-3 flex items-baseline gap-2">
                  <span className="serif-headline text-4xl font-semibold text-[color:var(--on-surface)] data-mono">{freqValue}</span>
                  <span className="label-caps text-xs text-[color:var(--on-surface-variant)]">分钟</span>
                </div>
                <input
                  className="w-full"
                  max="60"
                  min="1"
                  type="range"
                  value={freqValue}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    form.setValue('monitor_frequency', v, { shouldValidate: true });
                  }}
                />
                <div className="flex justify-between mt-2 label-caps text-[10px] text-[color:var(--on-surface-variant)]/60 data-mono">
                  <span>1 分</span>
                  <span>15 分</span>
                  <span>60 分</span>
                </div>
              </div>

              {/* Timing Windows */}
              <div className="space-y-4">
                <div>
                  <label className="label-caps text-[10px] text-[color:var(--on-surface-variant)]/70 mb-2 block tracking-[0.15em]">启动窗口</label>
                  <input
                    type="time"
                    {...form.register('start_time')}
                    className="w-full px-4 py-3 rounded-lg bg-white/60 border-[0.5px] border-[color:var(--border-faint)] focus:outline-none focus:border-[color:var(--primary-gold)] focus:ring-2 focus:ring-[oklch(0.78_0.16_85/0.2)] transition-all text-sm data-mono text-[color:var(--on-surface)]"
                  />
                </div>
                <div>
                  <label className="label-caps text-[10px] text-[color:var(--on-surface-variant)]/70 mb-2 block tracking-[0.15em]">简报时间</label>
                  <input
                    type="time"
                    {...form.register('push_time')}
                    className="w-full px-4 py-3 rounded-lg bg-white/60 border-[0.5px] border-[color:var(--border-faint)] focus:outline-none focus:border-[color:var(--primary-gold)] focus:ring-2 focus:ring-[oklch(0.78_0.16_85/0.2)] transition-all text-sm data-mono text-[color:var(--on-surface)]"
                  />
                </div>
              </div>

              {/* Notification Toggles */}
              <div className="space-y-5">
                {/* Daily Briefing */}
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold text-[color:var(--on-surface)]">每日简报</p>
                    <p className="text-xs text-[color:var(--on-surface-variant)]/70 mt-0.5">每日结束时的汇总报告。</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => form.setValue('push_summary', !watched.push_summary)}
                    className={`w-11 h-6 rounded-full relative transition-all ${watched.push_summary ? 'toggle-on' : 'toggle-off'}`}
                  >
                    <div
                      className="absolute top-0.5 w-5 h-5 bg-white rounded-full shadow-sm transition-all"
                      style={{ right: watched.push_summary ? '0.125rem' : undefined, left: watched.push_summary ? undefined : '0.125rem' }}
                    />
                  </button>
                </div>
                {/* Instant Alerts */}
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold text-[color:var(--on-surface)]">即时预警</p>
                    <p className="text-xs text-[color:var(--on-surface-variant)]/70 mt-0.5">高优先级信号的即时推送。</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => form.setValue('alert_negative', !watched.alert_negative)}
                    className={`w-11 h-6 rounded-full relative transition-all ${watched.alert_negative ? 'toggle-on' : 'toggle-off'}`}
                  >
                    <div
                      className="absolute top-0.5 w-5 h-5 bg-white rounded-full shadow-sm transition-all"
                      style={{ right: watched.alert_negative ? '0.125rem' : undefined, left: watched.alert_negative ? undefined : '0.125rem' }}
                    />
                  </button>
                </div>
                {/* Vision Pipeline */}
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold text-[color:var(--on-surface)]">视觉管线</p>
                    <p className="text-xs text-[color:var(--on-surface-variant)]/70 mt-0.5">自动解析图像证据。</p>
                  </div>
                  <button
                    type="button"
                    className="toggle-on w-11 h-6 rounded-full relative transition-all"
                  >
                    <div className="absolute right-0.5 top-0.5 w-5 h-5 bg-white rounded-full shadow-sm" />
                  </button>
                </div>
              </div>
            </div>
          </form>
        </section>

        {/* Footer status */}
        <div className="col-span-12 flex justify-between items-center pt-4">
          <p className="text-xs text-[color:var(--on-surface-variant)]/60 label-caps">
            {save.isPending ? '保存中...' : '改动将自动保存'}
          </p>
        </div>
      </div>
    </div>
  );
}
