'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { authApi, radarApi } from '@/lib/api';

const pageTitles: Record<string, string> = {
  '/agent': 'Omnis Agent',
  '/dashboard': '总览仪表盘',
  '/list': '入库信息',
  '/settings/system': '系统设置',
  '/settings/push': '推送设置',
  '/settings/llm': '模型配置',
  '/settings/account': '账号设置',
};

function getPageTitle(pathname: string): string {
  if (pageTitles[pathname]) return pageTitles[pathname];
  if (pathname.startsWith('/settings')) return '系统设置';
  return 'Omnis';
}

export function Topbar() {
  const pathname = usePathname();
  const router = useRouter();

  const { data: user } = useQuery({
    queryKey: ['current-user'],
    queryFn: () => authApi.me(),
  });

  const title = getPageTitle(pathname);

  return (
    <header
      className="sticky top-0 z-30 h-16 flex items-center justify-between px-8 border-b border-[var(--border-faint)]"
      style={{
        background: 'radial-gradient(ellipse 80% 60% at 50% 0%, var(--bg-inner) 0%, var(--bg-outer) 100%)',
        backgroundAttachment: 'fixed',
      }}
    >
      {/* Left: page title */}
      <h1 className="serif-headline text-xl font-bold" style={{ color: 'var(--on-surface)' }}>
        {title}
      </h1>

      {/* Right: status badges + avatar */}
      <div className="flex items-center gap-2">
        <StatusBadges />
        {user && <AvatarDropdown user={user} router={router} />}
      </div>
    </header>
  );
}

function StatusBadges() {
  const { data: schedStatus } = useQuery({
    queryKey: ['scheduler-status'],
    queryFn: () => radarApi.schedulerStatus(),
    refetchInterval: 30_000,
  });

  const isActive = schedStatus?.active;

  return (
    <>
      {/* Scheduler status */}
      <span
        className="flex items-center gap-2 px-3 py-1 rounded-full border transition-all"
        style={{
          background: isActive ? 'oklch(0.78 0.16 85 / 0.08)' : 'rgba(0,0,0,0.02)',
          borderColor: isActive ? 'oklch(0.78 0.16 85 / 0.15)' : 'var(--border-faint)',
        }}
      >
        <span
          className={`w-1.5 h-1.5 rounded-full transition-all ${isActive ? 'bg-emerald-500' : 'bg-gray-400'}`}
          style={isActive ? { boxShadow: '0 0 0 0 #10b981', animation: 'pulse-ring 2s infinite' } : {}}
        />
        <span className="label-caps text-[10px] font-bold" style={{ color: isActive ? 'var(--primary-gold)' : 'var(--on-surface-variant)' }}>
          调度器-{isActive ? '开启' : '关闭'}
        </span>
      </span>
    </>
  );
}

function AvatarDropdown({
  user,
  router,
}: {
  user: { nickname?: string; email?: string };
  router: ReturnType<typeof useRouter>;
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  const handleLogout = () => {
    localStorage.removeItem('mediaradar_token');
    router.push('/login');
  };

  return (
    <div className="relative ml-1" ref={menuRef}>
      <button
        onClick={() => setOpen(!open)}
        className="w-8 h-8 rounded-full bg-white/50 backdrop-blur border border-black/5 flex items-center justify-center cursor-pointer hover:border-[var(--primary-gold)] transition-colors overflow-hidden"
      >
        <span className="text-[11px] font-semibold" style={{ color: 'var(--on-surface-variant)' }}>
          {user.nickname?.[0]?.toUpperCase() || 'U'}
        </span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            className="absolute right-0 top-full mt-2 z-20 w-44 rounded-xl border shadow-lg overflow-hidden"
            style={{ background: 'white', borderColor: 'var(--border-faint)' }}
          >
            <Link
              href="/settings/account"
              onClick={() => setOpen(false)}
              className="flex items-center gap-3 px-4 py-3 text-sm transition-colors hover:bg-black/5"
              style={{ color: 'var(--on-surface)' }}
            >
              <span className="material-symbols-outlined text-lg">settings</span>
              账号设置
            </Link>
            <div className="h-px" style={{ background: 'var(--border-faint)' }} />
            <button
              onClick={handleLogout}
              className="flex items-center gap-3 w-full text-left px-4 py-3 text-sm transition-colors hover:bg-black/5"
              style={{ color: 'var(--status-error)' }}
            >
              <span className="material-symbols-outlined text-lg">logout</span>
              退出登录
            </button>
          </div>
        </>
      )}
    </div>
  );
}
