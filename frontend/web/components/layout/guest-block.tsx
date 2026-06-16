'use client';

import { useRouter } from 'next/navigation';
import { isGuest } from '@/lib/auth-client';
import { useEffect, useState } from 'react';

interface GuestBlockProps {
  /** 显示在 CTA 中的功能名称 */
  feature: string;
  /** 是否全屏居中（默认 true） */
  fullPage?: boolean;
}

/**
 * 游客拦截组件：检测当前用户是否为游客，若是则显示升级提示。
 * 适用于 Agent 聊天、设置页等游客不可访问的页面。
 */
export function GuestBlock({ feature, fullPage = true }: GuestBlockProps) {
  const router = useRouter();
  const [guest, setGuest] = useState(false);

  useEffect(() => {
    setGuest(isGuest());
  }, []);

  if (!guest) return null;

  const content = (
    <div className="flex flex-col items-center justify-center gap-4 text-center">
      <span className="material-symbols-outlined text-4xl" style={{ color: 'var(--primary-gold)' }}>
        lock
      </span>
      <h2 className="serif-headline text-xl font-bold" style={{ color: 'var(--on-surface)' }}>
        功能不可用
      </h2>
      <p className="text-sm max-w-xs" style={{ color: 'var(--on-surface-variant)' }}>
        {feature} 需要注册账号后使用。
        登录或注册后，即可使用完整功能。
      </p>
      <div className="flex gap-3 mt-2">
        <button
          type="button"
          onClick={() => router.push('/login')}
          className="brushed-gold brushed-gold-text font-bold px-6 py-2.5 rounded-lg text-sm transition-all hover:opacity-90"
        >
          登录 / 注册
        </button>
      </div>
    </div>
  );

  if (fullPage) {
    return (
      <div className="flex min-h-[60vh] w-full items-center justify-center px-4">
        {content}
      </div>
    );
  }

  return content;
}
