'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Skeleton } from '@/components/ui/skeleton';
import { pushApi, type PushConfig } from '@/lib/api';
import { toast } from 'sonner';
import { GuestBlock } from '@/components/layout/guest-block';
import { isGuest } from '@/lib/auth-client';

const emailSchema = z.object({
  enabled: z.boolean(),
  risk_min_level: z.number().min(1).max(5),
  smtp_host: z.string().min(1, 'SMTP 主机必填'),
  smtp_port: z.number().min(1).max(65535),
  smtp_user: z.string().min(1, '用户名必填'),
  smtp_password: z.string().optional(),
  smtp_use_tls: z.boolean(),
  from_addr: z.string().email('发件人邮箱格式错误'),
  to_addrs: z.array(z.string().email('收件人邮箱格式错误')).min(1, '至少 1 个收件人'),
});

const webhookSchema = z.object({
  enabled: z.boolean(),
  risk_min_level: z.number().min(1).max(5),
  webhook_url: z.string().url('Webhook URL 格式错误'),
});

type EmailValues = z.infer<typeof emailSchema>;
type WebhookValues = z.infer<typeof webhookSchema>;

const tabs = [
  { id: 'email', label: '邮件配置' },
  { id: 'wecom', label: '企业微信' },
  { id: 'feishu', label: '飞书' },
] as const;

const INPUT_CLASS =
  'w-full px-4 py-3 rounded-lg bg-white/70 border-[0.5px] border-[color:var(--border-faint)] focus:outline-none focus:border-[color:var(--primary-gold)] focus:ring-2 focus:ring-[oklch(0.78_0.16_85/0.2)] transition-all text-sm text-[color:var(--on-surface)] placeholder:text-[color:var(--on-surface-variant)]/40';

export default function PushSettingsPage() {
  // 游客拦截
  if (isGuest()) {
    return <GuestBlock feature="推送设置" />;
  }
  const [activeTab, setActiveTab] = useState<string>('email');

  const { data: configs, isLoading } = useQuery({
    queryKey: ['push-configs'],
    queryFn: () => pushApi.configs(),
  });

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Sub-tabs with active-tab-line */}
      <div className="flex border-b border-[color:var(--border-faint)] mb-8 gap-10">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setActiveTab(t.id)}
            className={`label-caps text-[11px] pb-4 relative transition-colors ${
              activeTab === t.id
                ? 'text-[color:var(--primary-gold)]'
                : 'text-[color:var(--on-surface-variant)] hover:text-[color:var(--primary-gold)]'
            }`}
          >
            {t.label}
            {activeTab === t.id && (
              <div className="active-tab-line absolute inset-x-0 bottom-0 w-full h-[2px] bg-[color:var(--primary-gold)]" />
            )}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="glass-slab rounded-xl p-5">
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <div className="space-y-6">
          {activeTab === 'email' && <EmailForm config={configs?.email} />}
          {activeTab === 'wecom' && <WebhookForm channel="wecom" name="WeCom" config={configs?.wecom} />}
          {activeTab === 'feishu' && <WebhookForm channel="feishu" name="Feishu (Lark)" config={configs?.feishu} />}
        </div>
      )}
    </div>
  );
}

function EmailForm({ config }: { config?: PushConfig }) {
  const qc = useQueryClient();
  const [emailDraft, setEmailDraft] = useState('');
  const form = useForm<EmailValues>({
    resolver: zodResolver(emailSchema),
    values: config as EmailValues | undefined,
    defaultValues: config as EmailValues | undefined,
  });
  const watched = form.watch();
  const toAddrs = watched.to_addrs ?? [];

  const save = useMutation({
    mutationFn: (v: EmailValues) => pushApi.save('email', v),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['push-configs'] });
      toast.success('邮件配置已保存');
    },
  });

  const test = useMutation({
    mutationFn: () => pushApi.test('email'),
    onSuccess: (r) => toast.success(r.msg || '测试成功'),
  });

  return (
    <section className="glass-slab rounded-xl p-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h2 className="serif-headline text-2xl text-[color:var(--on-surface)]">邮件服务器配置</h2>
          <p className="label-caps text-[10px] text-[color:var(--on-surface-variant)] mt-1">SMTP 协议设置</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="label-caps text-[10px] text-[color:var(--on-surface-variant)]">启用推送</span>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              className="sr-only peer switch-input"
              checked={watched.enabled}
              onChange={(e) => form.setValue('enabled', e.target.checked)}
            />
            <div className="w-11 h-6 bg-[color:var(--border-faint)] rounded-full transition-colors switch-bg" />
            <div className="absolute left-1 top-1 w-4 h-4 bg-white rounded-full transition-transform switch-dot" />
          </label>
        </div>
      </div>

      <form onSubmit={form.handleSubmit((v) => save.mutate(v))}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-6">
          <div className="space-y-2">
            <label className="label-caps text-[10px] text-[color:var(--on-surface-variant)]">SMTP 主机</label>
            <input {...form.register('smtp_host')} placeholder="smtp.mediaradar.ai" className={INPUT_CLASS} type="text" />
          </div>
          <div className="space-y-2">
            <label className="label-caps text-[10px] text-[color:var(--on-surface-variant)]">端口</label>
            <input {...form.register('smtp_port', { valueAsNumber: true })} placeholder="465" className={INPUT_CLASS} type="number" />
          </div>
          <div className="space-y-2">
            <label className="label-caps text-[10px] text-[color:var(--on-surface-variant)]">认证用户</label>
            <input {...form.register('smtp_user')} placeholder="admin@mediaradar.ai" className={INPUT_CLASS} type="text" />
          </div>
          <div className="space-y-2">
            <label className="label-caps text-[10px] text-[color:var(--on-surface-variant)]">密码</label>
            <input {...form.register('smtp_password')} placeholder="留空保留原密码" className={INPUT_CLASS} type="password" />
          </div>
          <div className="space-y-2 md:col-span-2">
            <label className="label-caps text-[10px] text-[color:var(--on-surface-variant)]">发件人邮箱</label>
            <input {...form.register('from_addr')} placeholder="alerts-no-reply@mediaradar.ai" className={INPUT_CLASS} type="email" />
          </div>
        </div>

        <div className="mt-8 pt-8 border-t border-[color:var(--border-faint)] space-y-6">
          <div className="space-y-4">
            <label className="label-caps text-[10px] text-[color:var(--on-surface-variant)]">收件人列表</label>
            <div className="flex gap-2">
              <input
                type="email"
                value={emailDraft}
                onChange={(e) => setEmailDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    if (emailDraft) {
                      form.setValue('to_addrs', [...toAddrs, emailDraft], { shouldValidate: true });
                      setEmailDraft('');
                    }
                  }
                }}
                placeholder="添加邮箱地址..."
                className={INPUT_CLASS + ' flex-1'}
              />
              <button
                type="button"
                onClick={() => {
                  if (emailDraft) {
                    form.setValue('to_addrs', [...toAddrs, emailDraft], { shouldValidate: true });
                    setEmailDraft('');
                  }
                }}
                className="brushed-gold w-12 flex items-center justify-center rounded-lg hover:opacity-95 transition-opacity text-[color:oklch(0.2_0.05_85)]"
              >
                <span className="material-symbols-outlined">add</span>
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {toAddrs.map((a) => (
                <span
                  key={a}
                  className="inline-flex items-center gap-2 bg-white/70 text-[color:var(--on-surface)] px-3 py-1.5 rounded-full label-caps text-[10px] border border-[color:var(--border-faint)]"
                >
                  {a}
                  <button
                    type="button"
                    onClick={() => form.setValue('to_addrs', toAddrs.filter((x) => x !== a), { shouldValidate: true })}
                    className="hover:text-[color:var(--status-error)] transition-colors"
                  >
                    <span className="material-symbols-outlined text-[16px]">close</span>
                  </button>
                </span>
              ))}
              {toAddrs.length === 0 && (
                <span className="text-xs text-[color:var(--on-surface-faint)]">暂无收件人</span>
              )}
            </div>
          </div>

          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 caustic-card rounded-xl p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="material-symbols-outlined text-[color:var(--primary-gold)]" style={{ fontVariationSettings: "'FILL' 1" }}>lock</span>
                <div>
                  <p className="font-semibold text-sm text-[color:var(--on-surface)]">TLS 加密</p>
                  <p className="text-[12px] text-[color:var(--on-surface-variant)]">强制安全连接</p>
                </div>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  className="sr-only peer switch-input"
                  checked={watched.smtp_use_tls}
                  onChange={(e) => form.setValue('smtp_use_tls', e.target.checked)}
                />
                <div className="w-11 h-6 bg-[color:var(--border-faint)] rounded-full transition-colors switch-bg" />
                <div className="absolute left-1 top-1 w-4 h-4 bg-white rounded-full transition-transform switch-dot" />
              </label>
            </div>
            <div className="w-full md:w-64 caustic-card rounded-xl p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="material-symbols-outlined text-[color:var(--primary-gold)]">warning</span>
                <div>
                  <p className="font-semibold text-sm text-[color:var(--on-surface)]">风险等级</p>
                  <p className="text-[12px] text-[color:var(--on-surface-variant)]">最低阈值</p>
                </div>
              </div>
              <input
                type="number"
                min={1}
                max={5}
                {...form.register('risk_min_level', { valueAsNumber: true })}
                className="w-12 bg-white border-none text-center font-bold text-[color:var(--primary-gold)] focus:ring-0"
              />
            </div>
          </div>
        </div>

        <div className="mt-8 flex justify-end gap-3">
          <button
            type="button"
            onClick={() => test.mutate()}
            disabled={test.isPending || !watched.enabled}
            className="px-6 py-2.5 rounded-lg label-caps text-[10px] text-[color:var(--on-surface-variant)] border border-[color:var(--border-faint)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            发送测试
          </button>
          <button
            type="submit"
            disabled={save.isPending}
            className="brushed-gold px-6 py-2.5 rounded-lg label-caps text-[10px] flex items-center gap-2 hover:opacity-95 shadow-lg transition-all disabled:opacity-50 text-[color:oklch(0.2_0.05_85)]"
          >
            {save.isPending ? (
              <span className="material-symbols-outlined text-[18px] animate-spin">sync</span>
            ) : (
              <span className="material-symbols-outlined text-[18px]" style={{ fontVariationSettings: "'FILL' 1" }}>save</span>
            )}
            保存配置
          </button>
        </div>
      </form>
    </section>
  );
}

function WebhookForm({ channel, name, config }: { channel: string; name: string; config?: PushConfig }) {
  const qc = useQueryClient();
  const form = useForm<WebhookValues>({
    resolver: zodResolver(webhookSchema),
    values: config as WebhookValues | undefined,
    defaultValues: config as WebhookValues | undefined,
  });
  const watched = form.watch();

  const save = useMutation({
    mutationFn: (v: WebhookValues) => pushApi.save(channel, v),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['push-configs'] });
      toast.success(`${name} 配置已保存`);
    },
  });
  const test = useMutation({
    mutationFn: () => pushApi.test(channel),
    onSuccess: (r) => toast.success(r.msg || '测试成功'),
  });

  const isFeishu = channel === 'feishu';
  const iconName = isFeishu ? 'security' : 'report';
  const riskLabel = isFeishu ? '优先级阈值' : '预警风险等级';
  const riskDesc = isFeishu ? '最低预警级别' : '1-5 级敏感度';

  return (
    <section className="glass-slab rounded-xl p-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h2 className="serif-headline text-2xl text-[color:var(--on-surface)]">
            {name} {isFeishu ? '(Lark)' : ''} Webhook
          </h2>
          <p className="label-caps text-[10px] text-[color:var(--on-surface-variant)] mt-1">
            {isFeishu ? '企业协作消息' : '企业微信集成'}
          </p>
        </div>
        <label className="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            className="sr-only peer switch-input"
            checked={watched.enabled}
            onChange={(e) => form.setValue('enabled', e.target.checked)}
          />
          <div className="w-11 h-6 bg-[color:var(--border-faint)] rounded-full transition-colors switch-bg" />
          <div className="absolute left-1 top-1 w-4 h-4 bg-white rounded-full transition-transform switch-dot" />
        </label>
      </div>

      <form onSubmit={form.handleSubmit((v) => save.mutate(v))}>
        <div className="space-y-6">
          <div className="space-y-2">
            <label className="label-caps text-[10px] text-[color:var(--on-surface-variant)]">
              {isFeishu ? 'Webhook 地址' : 'Webhook URL'}
            </label>
            <input
              {...form.register('webhook_url')}
              placeholder={isFeishu ? 'https://open.feishu.cn/open-apis/bot/v2/hook/...' : 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...'}
              className={INPUT_CLASS}
              type="text"
            />
          </div>
          <div className="w-full md:w-80 caustic-card rounded-xl p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="material-symbols-outlined text-[color:var(--primary-gold)]">{iconName}</span>
              <div>
                <p className="font-semibold text-sm text-[color:var(--on-surface)]">{riskLabel}</p>
                <p className="text-[12px] text-[color:var(--on-surface-variant)]">{riskDesc}</p>
              </div>
            </div>
            <input
              type="number"
              min={1}
              max={5}
              {...form.register('risk_min_level', { valueAsNumber: true })}
              className="w-12 bg-white border-none text-center font-bold text-[color:var(--primary-gold)] focus:ring-0"
            />
          </div>
        </div>

        <div className="mt-8 flex justify-end gap-3">
          <button
            type="button"
            onClick={() => test.mutate()}
            disabled={test.isPending || !watched.enabled}
            className="px-6 py-2.5 rounded-lg label-caps text-[10px] text-[color:var(--on-surface-variant)] border border-[color:var(--border-faint)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isFeishu ? '发送测试消息' : '测试 Webhook'}
          </button>
          <button
            type="submit"
            disabled={save.isPending}
            className="brushed-gold px-6 py-2.5 rounded-lg label-caps text-[10px] flex items-center gap-2 hover:opacity-95 shadow-lg transition-all disabled:opacity-50 text-[color:oklch(0.2_0.05_85)]"
          >
            {save.isPending ? (
              <span className="material-symbols-outlined text-[18px] animate-spin">sync</span>
            ) : (
              <span className="material-symbols-outlined text-[18px]" style={{ fontVariationSettings: "'FILL' 1" }}>
                {isFeishu ? 'cloud_done' : 'check_circle'}
              </span>
            )}
            保存配置
          </button>
        </div>
      </form>
    </section>
  );
}
