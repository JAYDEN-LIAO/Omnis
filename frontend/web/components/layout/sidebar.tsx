'use client';

import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';
import { mainNav } from './sidebar-nav';
import { useSidebarStore } from '@/stores/sidebar-store';
import pkg from '@/package.json';

export function Sidebar() {
  const pathname = usePathname();
  const { collapsed, toggle } = useSidebarStore();

  const isActive = (href: string) => {
    if (href === '/agent') return pathname === '/agent';
    if (href === '/settings/system') return pathname.startsWith('/settings');
    return pathname === href;
  };

  const sidebarWidth = collapsed ? 80 : 168;

  return (
    <>
      <style>{`:root { --sidebar-w: ${sidebarWidth + 16}px; }`}</style>

      <aside
        className={`fixed left-4 top-4 bottom-4 z-40 glass-slab rounded-xl flex flex-col py-8 ${collapsed ? '' : 'sidebar-expanded'}`}
        style={{
          width: sidebarWidth,
          transition: 'width 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
          willChange: 'width',
        }}
      >
        {/* Toggle button */}
        <button
          onClick={toggle}
          className="absolute -right-3 top-12 z-10 w-6 h-6 bg-white border border-[var(--border-refined)] shadow-md rounded-full flex items-center justify-center text-[var(--on-surface-variant)] hover:scale-110 transition-transform"
          aria-label="Toggle sidebar"
          style={{ transform: collapsed ? 'rotate(0deg)' : 'rotate(180deg)', transition: 'transform 0.4s ease' }}
        >
          <span className="material-symbols-outlined text-sm font-bold">chevron_right</span>
        </button>

        {/* Brand */}
        <div className={`mb-2 flex items-center h-20 ${collapsed ? 'pl-3 pr-6' : 'pl-3 pr-6 gap-3'}`}>
          {/* Logo — same left offset in both states */}
          <div className="shrink-0 flex items-center justify-center">
            <Image
              src="/logo.svg"
              alt="Omnis"
              width={52}
              height={28}
              priority
              unoptimized
            />
          </div>

          {/* Version badge — only when expanded */}
          {!collapsed && (
            <span className="text-[7px] label-caps px-1.5 py-0.5 rounded border shrink-0" style={{ borderColor: 'oklch(0.78 0.16 85 / 0.3)', color: 'var(--primary-gold)' }}>
              {`v${pkg.version}`}
            </span>
          )}
        </div>

        {/* Main navigation */}
        <nav className="flex-1 flex flex-col px-3 gap-1 overflow-x-hidden">
          {mainNav.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center px-4 py-3 rounded-lg transition-colors duration-200 ${
                  active
                    ? 'nav-active gold-glow-ambient'
                    : 'text-[var(--on-surface-variant)] hover:text-[var(--on-surface)] hover:bg-black/5'
                }`}
              >
                <span className="material-symbols-outlined shrink-0">{item.icon}</span>
                <span
                  className={`sidebar-nav-label label-caps text-[12px] ${
                    collapsed ? '' : ''
                  }`}
                >
                  {item.title}
                </span>
              </Link>
            );
          })}
        </nav>

        {/* Bottom section */}
        <div className="px-3 border-t border-black/5 pt-4">
          <div
            className="flex items-center px-4 py-3 rounded-lg cursor-not-allowed"
            style={{ color: 'var(--on-surface-faint)', opacity: 0.5 }}
          >
            <span className="material-symbols-outlined shrink-0">help</span>
            <span className="sidebar-nav-label label-caps text-[12px]">帮助支持</span>
          </div>
        </div>
      </aside>
    </>
  );
}
