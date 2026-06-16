'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { isGuest, getGuestRemainingTime, formatGuestTime } from '@/lib/auth-client';

export function GuestBanner() {
  const router = useRouter();
  const [remaining, setRemaining] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!isGuest()) {
      setVisible(false);
      return;
    }
    setVisible(true);

    const tick = () => setRemaining(getGuestRemainingTime());
    tick();
    const interval = setInterval(tick, 5_000);
    return () => clearInterval(interval);
  }, []);

  if (!visible) return null;

  const expired = remaining <= 0;

  return (
    <div
      className="flex items-center justify-between gap-4 px-6 py-2 text-sm border-b"
      style={{
        background: 'oklch(0.95 0.05 85 / 0.5)',
        borderColor: 'oklch(0.85 0.1 85 / 0.3)',
        color: 'oklch(0.4 0.08 85)',
      }}
    >
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-base">visibility</span>
        <span>
          <strong>游客模式</strong>
          {expired
            ? ' · 会话已过期'
            : ` · 会话剩余 ${formatGuestTime(remaining)}`}
          · 部分功能受限
        </span>
      </div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => router.push('/login')}
          className="text-xs font-semibold underline-offset-2 hover:underline"
          style={{ color: 'oklch(0.4 0.08 85)' }}
        >
          注册/登录
        </button>
      </div>
    </div>
  );
}
