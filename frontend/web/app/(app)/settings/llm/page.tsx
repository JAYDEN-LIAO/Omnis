'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Skeleton } from '@/components/ui/skeleton';
import { llmApi, authApi, type LLMConfigItem } from '@/lib/api';
import { toast } from 'sonner';
import { GuestBlock } from '@/components/layout/guest-block';
import { isGuest } from '@/lib/auth-client';

const ROLE_CLASS: Record<string, string> = {
  default: 'role-default',
  assistant: 'role-assistant',
  embedding: 'role-vector',
  vision: 'role-vision',
};

const AGENT_LABELS: Record<string, { title: string; desc: string }> = {
  default: { title: '通用模型', desc: '未单独配置的 AI 能力默认使用的模型。各角色可独立配置覆盖。' },
  assistant: { title: '对话模型', desc: 'AI 助手的主模型，负责理解用户意图、规划任务步骤、调用工具。' },
  embedding: { title: '向量嵌入', desc: '将文本转为向量，用于语义聚类和相似度检索。' },
  vision: { title: '图像识别', desc: '分析图片内容、提取文字信息，用于视觉类分析任务。' },
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
      </div>

      {/* ── 邀请码解锁区域 ── */}
      <InviteCodeSection />

      <div className="h-12" />
    </div>
  );
}

function InviteCodeSection() {
  const [code, setCode] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  // 查询当前权限状态
  const { data: accessData, isLoading: accessLoading } = useQuery({
    queryKey: ['invite-status'],
    queryFn: () => authApi.inviteStatus(),
  });

  const hasAccess = accessData?.has_system_access;

  const handleRedeem = async () => {
    if (!code.trim()) { toast.error('请输入邀请码'); return; }
    setStatus('loading');
    try {
      const res = await authApi.redeemInvite(code.trim());
      setStatus('success');
      setMessage(res.msg || '邀请码兑换成功');
      toast.success(res.msg || '邀请码兑换成功');
      // 刷新状态
      window.location.reload();
    } catch (err: unknown) {
      setStatus('error');
      const msg = (err as { message?: string })?.message || '兑换失败，请检查邀请码是否正确';
      setMessage(msg);
      toast.error(msg);
    }
  };

  return (
    <div className="glass-slab rounded-xl overflow-hidden mt-6">
      <div className="p-8">
        <div className="flex items-center gap-2 mb-1">
          <span className="material-symbols-outlined text-lg text-[color:var(--primary-gold)]">vpn_key</span>
          <h3 className="serif-headline text-xl text-[color:var(--on-surface)]">邀请码解锁</h3>
        </div>
        <p className="text-sm text-[color:var(--on-surface-variant)] mb-6">
          {hasAccess
            ? '✅ 当前账号已拥有系统 Key 权限，无需再次兑换。'
            : '输入邀请码解锁系统预置的 API Key，无需自行配置即可使用 AI 智能体。'}
        </p>

        {!hasAccess && (
          <div className="flex items-end gap-3">
            <div className="flex-1 max-w-sm">
              <label className="block text-xs font-semibold text-[color:var(--on-surface-variant)] label-caps mb-1">
                邀请码
              </label>
              <input
                type="text"
                value={code}
                onChange={(e) => { setCode(e.target.value); setStatus('idle'); }}
                placeholder="请输入邀请码"
                className="w-full bg-white/70 border border-[color:var(--border-faint)] focus:border-[color:var(--primary-gold)] focus:ring-2 focus:ring-[oklch(0.78_0.16_85/0.15)] rounded-lg px-3 py-2 text-sm transition-all outline-none uppercase"
                onKeyDown={(e) => { if (e.key === 'Enter') handleRedeem(); }}
              />
              {status === 'error' && message && (
                <p className="text-xs text-red-500 mt-1">{message}</p>
              )}
              {status === 'success' && message && (
                <p className="text-xs text-green-600 mt-1">{message}</p>
              )}
            </div>
            <button
              type="button"
              onClick={handleRedeem}
              disabled={status === 'loading'}
              className="brushed-gold hover:opacity-95 px-5 py-2 rounded-lg text-sm font-bold text-white transition-all disabled:opacity-50 flex items-center gap-2"
            >
              {status === 'loading' ? (
                <span className="material-symbols-outlined text-sm animate-spin">sync</span>
              ) : (
                <span className="material-symbols-outlined text-sm">check</span>
              )}
              兑换
            </button>
          </div>
        )}
      </div>
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
  const [baseUrl, setBaseUrl] = useState(info.effective_base_url);
  const [model, setModel] = useState(info.effective_model);
  const label = AGENT_LABELS[agent] ?? { title: info.label, desc: info.role || '' };
  const roleClass = ROLE_CLASS[agent] || 'role-default';

  const save = useMutation({
    mutationFn: async () => {
      const newConfig = { api_key: apiKey || undefined, base_url: baseUrl || undefined, model: model || undefined };
      // 先测试新配置，通过后才保存
      const testResult = await llmApi.test(agent, newConfig);
      if (!testResult || testResult.code !== 200) {
        throw new Error(testResult?.msg || '连接测试失败');
      }
      return llmApi.save(agent, newConfig);
    },
    onSuccess: (r) => {
      toast.success(r.msg || '配置已保存');
      setApiKey('');
      onSaved();
    },
    onError: (e) => {
      toast.error(e.message || '保存失败，配置未更改');
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
            {info.uses_default ? '使用默认' : '已配置'}
          </span>
        </div>
        <h3 className="serif-headline text-2xl text-[color:var(--on-surface)] mb-2">{label.title}</h3>
        <p className="text-sm text-[color:var(--on-surface-variant)]">{label.desc}</p>
        <div className="mt-4 flex items-center gap-2">
          <span className={`inline-block w-2 h-2 rounded-full ${info.has_key ? 'bg-green-500' : 'bg-yellow-400'}`} />
          <span className="text-xs font-medium text-[color:var(--on-surface)]">
            {info.uses_default ? '使用默认配额' : '已自定义'}
          </span>
        </div>
      </div>

      {/* Right form panel */}
      <div className="lg:w-2/3 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="col-span-full md:col-span-2">
          <label className="block text-xs font-semibold text-[color:var(--on-surface-variant)] label-caps mb-1">API 地址</label>
          <input
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={info.effective_base_url || 'https://api.openai.com/v1'}
            className={INPUT_CLASS}
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-[color:var(--on-surface-variant)] label-caps mb-1">模型名称</label>
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={info.effective_model || info.default_model || 'deepseek-chat'}
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
