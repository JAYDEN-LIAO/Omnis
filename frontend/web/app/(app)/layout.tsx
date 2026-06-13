'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { Sidebar } from '@/components/layout/sidebar';
import { Topbar } from '@/components/layout/topbar';
import { isAuthenticated } from '@/lib/auth-client';
import { useSidebarStore } from '@/stores/sidebar-store';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checking, setChecking] = useState(true);
  const collapsed = useSidebarStore((s) => s.collapsed);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace(`/login?redirect=${encodeURIComponent(pathname)}`);
    } else {
      setChecking(false);
    }
  }, [router, pathname]);

  if (checking) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-background">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground/20 border-t-muted-foreground/60" />
      </div>
    );
  }

  const sidebarWidth = collapsed ? 96 : 296; // sidebar width + left-4 offset

  return (
    <div className="relative min-h-screen">
      <div className="interlaced-grid" />
      <Sidebar />
      <main
        className="relative z-10 min-h-screen"
        style={{ marginLeft: sidebarWidth, transition: 'margin-left 0.4s cubic-bezier(0.4, 0, 0.2, 1)' }}
      >
        <Topbar />
        <div className="p-6 md:p-8">{children}</div>
      </main>
    </div>
  );
}
