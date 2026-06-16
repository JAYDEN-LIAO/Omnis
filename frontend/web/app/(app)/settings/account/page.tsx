'use client';

import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Skeleton } from '@/components/ui/skeleton';
import { authApi } from '@/lib/api';
import { toast } from 'sonner';
import { GuestBlock } from '@/components/layout/guest-block';
import { isGuest } from '@/lib/auth-client';

const NOTIFICATION_DETAILS: Record<string, { desc: string }> = {
  'Critical Alerts': { desc: '即时系统异常' },
  'Daily Summary': { desc: '精选绩效摘要' },
  'System Updates': { desc: '功能与维护' },
};

const initialNotifications: Record<string, boolean> = {
  'Critical Alerts': true,
  'Daily Summary': true,
  'System Updates': false,
};

const INPUT_CLASS =
  'w-full bg-white/70 border border-[color:var(--border-faint)] rounded-lg px-4 py-3 focus:border-[color:var(--primary-gold)] focus:ring-2 focus:ring-[oklch(0.78_0.16_85/0.2)] transition-all outline-none text-sm';

export default function AccountSettingsPage() {
  const qc = useQueryClient();
  const { data: user, isLoading } = useQuery({
    queryKey: ['current-user'],
    queryFn: () => authApi.me(),
  });

  const [nicknameDraft, setNicknameDraft] = useState('');

  useEffect(() => {
    if (user?.nickname) setNicknameDraft(user.nickname);
  }, [user?.nickname]);

  const [notifications, setNotifications] = useState<Record<string, boolean>>(initialNotifications);

  // Auto-save nickname on change (debounced 1.5s)
  const nicknameTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isInitialNickname = useRef(true);

  const saveProfile = useMutation({
    mutationFn: () => authApi.updateProfile(nicknameDraft),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['current-user'] });
    },
  });

  useEffect(() => {
    // Skip save on initial data load
    if (isInitialNickname.current) {
      isInitialNickname.current = false;
      return;
    }
    // Skip if nickname hasn't changed from the loaded value
    if (nicknameDraft === user?.nickname) return;
    if (nicknameTimer.current) clearTimeout(nicknameTimer.current);
    nicknameTimer.current = setTimeout(() => {
      if (nicknameDraft.trim()) saveProfile.mutate();
    }, 1500);
    return () => {
      if (nicknameTimer.current) clearTimeout(nicknameTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nicknameDraft]);

  const toggle = (label: string) =>
    setNotifications((prev) => ({ ...prev, [label]: !prev[label] }));

  const initials = user?.nickname
    ? user.nickname.slice(0, 2).toUpperCase()
    : user?.email
      ? user.email.slice(0, 2).toUpperCase()
      : 'U';

  const roleBadge = user?.role === 'admin' ? '管理员' : '用户';
  const authMethod = user?.oauth_provider ? `SSO: ${user.oauth_provider}` : '邮箱登录';

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-64 w-full rounded-xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    );
  }

  // 游客拦截
  if (isGuest()) {
    return <GuestBlock feature="账号设置" />;
  }

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 pb-8">
        {/* Left column: Profile + 2FA */}
        <div className="lg:col-span-2 space-y-6">
          {/* Profile information */}
          <section className="glass-slab rounded-xl p-8 tonal-shadow">
            <div className="flex flex-col md:flex-row items-start md:items-center gap-8 mb-10">
              <div className="relative group">
                <div className="w-24 h-24 rounded-full bg-[oklch(0.78_0.16_85/0.12)] flex items-center justify-center text-[color:var(--primary-gold)] serif-headline text-2xl border-2 border-[color:var(--primary-gold)]/20">
                  {initials}
                </div>
                <button
                  type="button"
                  className="absolute bottom-0 right-0 brushed-gold text-white p-1.5 rounded-full shadow-lg border-2 border-white transition-transform hover:scale-110 active:scale-95 brushed-gold-text"
                >
                  <span className="material-symbols-outlined text-[18px]">photo_camera</span>
                </button>
              </div>
              <div className="flex-1 space-y-1">
                <h2 className="serif-headline text-2xl text-[color:var(--on-surface)]">
                  {user?.nickname || '用户'}
                </h2>
                <div className="flex flex-wrap gap-x-4 gap-y-2 text-[color:var(--on-surface-variant)] text-sm">
                  <span className="flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-[18px] text-[color:var(--primary-gold)]">mail</span>
                    {user?.email || ''}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-[18px] text-[color:var(--primary-gold)]">verified_user</span>
                    {roleBadge}
                  </span>
                  <span className="flex items-center gap-1 label-caps text-[10px] px-2 py-0.5 bg-[oklch(0.78_0.16_85/0.12)] text-[color:var(--primary-gold)] rounded-full font-bold">
                    {authMethod}
                  </span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <label className="label-caps text-[10px] text-[color:var(--on-surface-variant)] font-bold">昵称</label>
                <div className="relative">
                  <input
                    type="text"
                    value={nicknameDraft}
                    onChange={(e) => setNicknameDraft(e.target.value)}
                    className={INPUT_CLASS + ' pr-10'}
                  />
                  <span className="material-symbols-outlined absolute right-3 top-3.5 text-[color:var(--on-surface-variant)] text-[20px]">edit</span>
                </div>
              </div>
              <div className="space-y-2">
                <label className="label-caps text-[10px] text-[color:var(--on-surface-variant)] font-bold">邮箱地址</label>
                <div className="relative">
                  <input
                    type="email"
                    defaultValue={user?.email || ''}
                    disabled
                    className="w-full bg-white/40 border border-[color:var(--border-faint)] text-[color:var(--on-surface-variant)]/60 rounded-lg px-4 py-3 cursor-not-allowed text-sm pr-10"
                  />
                  <span className="material-symbols-outlined absolute right-3 top-3.5 text-[color:var(--on-surface-variant)]/40 text-[20px]">lock</span>
                </div>
              </div>
            </div>

            <div className="mt-8 pt-6 border-t border-[color:var(--border-faint)] flex justify-end">
              {saveProfile.isPending && (
                <span className="text-xs text-[color:var(--on-surface-variant)]/60 flex items-center gap-1">
                  <span className="material-symbols-outlined text-sm animate-spin">sync</span>
                  保存中...
                </span>
              )}
            </div>
          </section>

          {/* 2FA Security Card */}
          <section className="glass-slab rounded-xl p-8 tonal-shadow">
            <div className="flex items-start gap-6">
              <div className="p-4 bg-[oklch(0.78_0.16_85/0.08)] rounded-xl text-[color:var(--primary-gold)] border border-[color:var(--primary-gold)]/10">
                <span className="material-symbols-outlined text-[32px]">shield_lock</span>
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <h2 className="serif-headline text-2xl text-[color:var(--on-surface)]">双因素认证</h2>
                  <span className="label-caps text-[10px] text-[color:var(--primary-gold)]/70 bg-[oklch(0.78_0.16_85/0.08)] border border-[color:var(--primary-gold)]/15 px-2 py-1 rounded font-bold">
                    即将推出
                  </span>
                </div>
                <p className="text-[color:var(--on-surface-variant)] mt-2 text-sm leading-relaxed">
                  通过额外的验证步骤保护您的账户。建议使用硬件密钥或身份验证器应用以获得最大安全性。
                </p>
                <div className="mt-6 p-4 bg-white/40 rounded-lg border border-dashed border-[color:var(--border-faint)] flex items-center justify-between opacity-60">
                  <div className="flex items-center gap-3 text-[color:var(--on-surface)] font-medium">
                    <span className="material-symbols-outlined text-[color:var(--on-surface-variant)]">phonelink_lock</span>
                    <span>启用身份验证器</span>
                  </div>
                  <div className="w-11 h-6 bg-[color:var(--border-faint)] rounded-full relative">
                    <div className="absolute top-[2px] left-[2px] bg-white w-5 h-5 rounded-full shadow-sm" />
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>

        {/* Right column: Notifications + Support */}
        <div className="space-y-6">
          {/* Notifications */}
          <section className="glass-slab rounded-xl p-6 tonal-shadow space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="serif-headline text-lg text-[color:var(--on-surface)]">通知</h2>
              <span className="material-symbols-outlined text-[color:var(--primary-gold)] bg-[oklch(0.78_0.16_85/0.08)] p-2 rounded-full">notifications_active</span>
            </div>
            <div className="space-y-3">
              {Object.entries(NOTIFICATION_DETAILS).map(([label, detail]) => (
                <div
                  key={label}
                  className="flex items-center justify-between p-4 bg-white/40 rounded-xl border border-[color:var(--border-faint)] hover:border-[color:var(--primary-gold)] transition-colors"
                >
                  <div className="space-y-0.5">
                    <p className="font-bold text-[color:var(--on-surface)] text-sm">{label}</p>
                    <p className="text-[11px] text-[color:var(--on-surface-variant)]">{detail.desc}</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={notifications[label] ?? false}
                      onChange={() => toggle(label)}
                    />
                    <div
                      className="w-10 h-5 rounded-full transition-colors relative"
                      style={{ background: notifications[label] ? 'var(--primary-gold)' : 'var(--border-faint)' }}
                    >
                      <div
                        className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow-sm transition-transform"
                        style={{ transform: notifications[label] ? 'translateX(20px)' : 'translateX(0)' }}
                      />
                    </div>
                  </label>
                </div>
              ))}
            </div>
          </section>

          {/* Help / Support banner */}
          <section className="brushed-gold rounded-xl p-6 shadow-lg shadow-[oklch(0.78_0.16_85/0.2)] relative overflow-hidden group brushed-gold-text">
            <div className="absolute -right-4 -top-4 w-24 h-24 bg-white/10 rounded-full blur-2xl group-hover:bg-white/20 transition-all duration-500" />
            <div className="relative z-10">
              <h3 className="serif-headline text-lg mb-2 text-[color:oklch(0.2_0.05_85)]">需要帮助？</h3>
              <p className="text-xs opacity-80 mb-4 leading-relaxed text-[color:oklch(0.2_0.05_85)]">
                我们的支持团队全天候为您解答配置问题。
              </p>
              <button
                type="button"
                className="w-full py-2 bg-white text-[color:var(--on-surface)] font-bold rounded-lg text-xs label-caps hover:bg-[color:var(--bg-inner)] transition-colors"
              >
                联系支持
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
