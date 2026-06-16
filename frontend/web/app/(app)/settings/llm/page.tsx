'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Skeleton } from '@/components/ui/skeleton';
import { llmApi, type LLMConfigItem } from '@/lib/api';
import { toast } from 'sonner';
import { GuestBlock } from '@/components/layout/guest-block';
import { isGuest } from '@/lib/auth-client';

const ROLE_CLASS: Record<string, string> = {
  default: 'role-default',
  analyst: 'role-analyst',
  reviewer: 'role-reviewer',
  embedding: 'role-vector',
  vision: 'role-vision',
};

const AGENT_LABELS: Record<string, { title: string; desc: string }> = {
  default: { title: '系统编排器', desc: '所有未分配查询和通用任务管理的主要路由引擎。' },
  analyst: { title: '数据智能', desc: '针对复杂模式识别、SQL 生成和趋势预测进行了优化。' },
  reviewer: { title: '质量控制', desc: '专注于事实核查和品牌语调一致性的关键评估代理。' },
  embedding: { title: '语义搜索', desc: '用于高维数据检索的嵌入和 RAG 管线管理。' },
  vision: { title: '感知引擎', desc: '专门处理图像解析、OCR 和视觉上下文理解。' },
};

const INPUT_CLASS =
  'w-full bg-white/70 border border-[color:var(--border-faint)] focus:border-[color:var(--primary-gold)] focus:ring-2 focus:ring-[oklch(0.78_0.16_85/0.15)] rounded-lg px-3 py-2 text-sm transition-all outline-none';

export default function LLMSettingsPage() {
  // 游客拦截
  if (isGuest()) {
    return <GuestBlock feature="模型配置" />;
  }
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ['llm-configs'], queryFn: () => llmApi.configs() });
  const [revealKey, setRevealKey] = useState<Record<string, boolean>>({});

  const bulkTest = useMutation({
    mutationFn: async () => {
      if (!data) return null;
      const results = await Promise.allSettled(
        Object.keys(data).map((agent) => llmApi.test(agent)),
      );
      const successCount = results.filter((r) => r.status === 'fulfilled' && r.value?.msg).length;
      return { successCount, total: results.length };
    },
    onSuccess: (r) => {
      if (r) toast.success(`${r.successCount}/${r.total} agents passed test`);
    },
  });

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Main canvas */}
      <div className="glass-slab rounded-xl overflow-hidden">
        <div className="divide-y divide-[color:var(--border-faint)]">
          {isLoading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="p-8">
                <Skeleton className="h-32 w-full" />
              </div>
            ))
          ) : (
            data &&
            Object.entries(data).map(([agent, info]) => (
              <AgentCard
                key={agent}
                agent={agent}
                info={info}
                revealed={!!revealKey[agent]}
                onToggleReveal={() => setRevealKey((r) => ({ ...r, [agent]: !r[agent] }))}
                onSaved={() => qc.invalidateQueries({ queryKey: ['llm-configs'] })}
              />
            ))
          )}
        </div>

        {/* Global actions footer */}
        <div className="p-6 bg-white/40 border-t border-[color:var(--border-faint)] flex items-center justify-between">
          <div className="flex items-center gap-2 text-[color:var(--on-surface-variant)]">
            <span className="material-symbols-outlined text-lg">info</span>
            <span className="text-xs">更改将影响所有活跃会话。</span>
          </div>
          <div>
            <button
              type="button"
              onClick={() => bulkTest.mutate()}
              disabled={bulkTest.isPending || isLoading}
              className="caustic-card px-6 py-2.5 rounded-lg text-sm font-bold text-[color:var(--on-surface)] hover:border-[color:var(--primary-gold)] transition-all flex items-center gap-2 group disabled:opacity-50"
            >
              <span className={`material-symbols-outlined text-lg ${bulkTest.isPending ? 'animate-spin' : 'group-hover:animate-spin'}`}>refresh</span>
              测试连接
            </button>
          </div>
        </div>
      </div>

      <div className="h-12" />
    </div>
  );
}

function AgentCard({
  agent,
  info,
  revealed,
  onToggleReveal,
  onSaved,
}: {
  agent: string;
  info: LLMConfigItem;
  revealed: boolean;
  onToggleReveal: () => void;
  onSaved: () => void;
}) {
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState(info.base_url);
  const [model, setModel] = useState(info.model);
  const label = AGENT_LABELS[agent] ?? { title: info.label, desc: info.role || '' };
  const roleClass = ROLE_CLASS[agent] || 'role-default';

  const save = useMutation({
    mutationFn: () => llmApi.save(agent, { api_key: apiKey || undefined, base_url: baseUrl || undefined, model: model || undefined }),
    onSuccess: (r) => {
      toast.success(r.msg || '配置已保存');
      setApiKey('');
      onSaved();
    },
  });

  const test = useMutation({
    mutationFn: () => llmApi.test(agent),
    onSuccess: (r) => toast.success(r.msg || '连接成功'),
  });

  return (
    <div className="p-8 flex flex-col lg:flex-row gap-8">
      {/* Left info panel */}
      <div className="lg:w-1/3">
        <div className="flex items-center gap-2 mb-3">
          <span className={`px-3 py-1 text-[10px] font-bold rounded-full label-caps ${roleClass}`}>
            {info.label}
          </span>
          <span
            className="label-caps text-[10px] px-2 py-0.5 bg-[color:var(--bg-inner)] text-[color:var(--on-surface-variant)] rounded"
          >
            {info.uses_default ? '待配置' : '已配置'}
          </span>
        </div>
        <h3 className="serif-headline text-2xl text-[color:var(--on-surface)] mb-2">{label.title}</h3>
        <p className="text-sm text-[color:var(--on-surface-variant)]">{label.desc}</p>
        <div className="mt-4 space-y-2">
          <div className="flex justify-between text-xs font-medium">
            <span className="text-[color:var(--on-surface-variant)]">默认模型:</span>
            <span className="text-[color:var(--on-surface)]">{info.default_model || '未设置'}</span>
          </div>
          <div className="flex justify-between text-xs font-medium">
            <span className="text-[color:var(--on-surface-variant)]">当前模型:</span>
            <span className={`data-mono ${info.effective_model ? 'text-[color:var(--on-surface)]' : 'text-[color:var(--on-surface-variant)]'}`}>
              {info.effective_model || '未激活'}
            </span>
          </div>
        </div>
      </div>

      {/* Right form panel */}
      <div className="lg:w-2/3 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="col-span-full md:col-span-2">
          <label className="block text-xs font-semibold text-[color:var(--on-surface-variant)] label-caps mb-1">接口地址</label>
          <input
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
            className={INPUT_CLASS}
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-[color:var(--on-surface-variant)] label-caps mb-1">模型标识</label>
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={info.default_model || 'gpt-4o'}
            className={INPUT_CLASS + ' data-mono'}
          />
        </div>
        <div className="relative">
          <label className="block text-xs font-semibold text-[color:var(--on-surface-variant)] label-caps mb-1">API 密钥</label>
          <div className="relative">
            <input
              type={revealed ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={info.has_key ? `${info.api_key_masked}（留空保留）` : 'sk-...'}
              className={INPUT_CLASS + ' pr-10'}
            />
            <button
              type="button"
              onClick={onToggleReveal}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[color:var(--on-surface-variant)] cursor-pointer"
            >
              <span className="material-symbols-outlined text-lg">
                {revealed ? 'visibility_off' : 'visibility'}
              </span>
            </button>
          </div>
        </div>
        <div className="col-span-full flex justify-end pt-2 gap-2">
          <button
            type="button"
            onClick={() => test.mutate()}
            disabled={test.isPending}
            className="caustic-card px-4 py-1.5 rounded-lg text-xs font-bold text-[color:var(--on-surface)] hover:border-[color:var(--primary-gold)] transition-all flex items-center gap-2 disabled:opacity-50"
          >
            {test.isPending ? (
              <span className="material-symbols-outlined text-sm animate-spin">sync</span>
            ) : (
              <span className="material-symbols-outlined text-sm">science</span>
            )}
            测试
          </button>
          <button
            type="button"
            onClick={() => save.mutate()}
            disabled={save.isPending}
            className="caustic-card px-4 py-1.5 rounded-lg text-xs font-bold text-[color:var(--on-surface)] hover:border-[color:var(--primary-gold)] transition-all flex items-center gap-2 disabled:opacity-50"
          >
            {save.isPending ? (
              <span className="material-symbols-outlined text-sm animate-spin">sync</span>
            ) : (
              <span className="material-symbols-outlined text-sm">save</span>
            )}
            保存更改
          </button>
        </div>
      </div>
    </div>
  );
}
