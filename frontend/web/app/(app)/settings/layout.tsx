'use client';

import { motion } from 'framer-motion';
import { usePathname } from 'next/navigation';
import Link from 'next/link';

const tabs = [
  { title: '关于', href: '/settings/system' },
  { title: '推送', href: '/settings/push' },
  { title: '模型', href: '/settings/llm' },
  { title: '账号', href: '/settings/account' },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div>
      {/* Underline-style sub-nav tabs */}
      <nav className="flex items-center gap-10 border-b border-[color:var(--border-faint)] mb-8">
        {tabs.map((tab) => {
          const active = pathname === tab.href;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`label-caps text-[11px] pb-4 relative transition-colors ${
                active
                  ? 'text-[color:var(--primary-gold)]'
                  : 'text-[color:var(--on-surface-variant)] hover:text-[color:var(--primary-gold)]'
              }`}
            >
              {tab.title}
              {active && (
                <div className="absolute inset-x-0 bottom-0 h-[2px] bg-[color:var(--primary-gold)]" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Content */}
      <motion.div
        key={pathname}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.15 }}
      >
        {children}
      </motion.div>
    </div>
  );
}
