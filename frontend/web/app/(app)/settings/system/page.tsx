'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { radarApi } from '@/lib/api';
import pkg from '@/package.json';

export default function AboutPage() {
  useEffect(() => { document.title = '关于 — Omnis'; }, []);

  const { data: schedStatus } = useQuery({
    queryKey: ['scheduler-status'],
    queryFn: () => radarApi.schedulerStatus(),
    refetchInterval: 15_000,
  });

  return (
    <div className="max-w-[1400px] mx-auto flex flex-col gap-8">
      {/* Hero card */}
      <div className="glass-slab rounded-2xl p-10 relative overflow-hidden">
        <div className="absolute -top-20 -right-20 w-64 h-64 rounded-full blur-3xl pointer-events-none" style={{ background: 'oklch(0.78 0.16 85 / 0.06)' }} />
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center" style={{ background: 'oklch(0.78 0.16 85 / 0.12)' }}>
              <span className="material-symbols-outlined text-2xl" style={{ color: 'var(--primary-gold)', fontVariationSettings: "'FILL' 1" }}>auto_awesome</span>
            </div>
            <div>
              <h1 className="serif-headline text-2xl font-bold" style={{ color: 'var(--on-surface)' }}>Omnis</h1>
              <p className="text-sm mt-0.5" style={{ color: 'var(--on-surface-variant)' }}>v{pkg.version} · 媒体信息智能平台</p>
            </div>
          </div>
          <p className="text-base leading-relaxed max-w-2xl mt-4" style={{ color: 'var(--on-surface-variant)' }}>
            Omnis 是一个基于 Multi-Agent 架构的媒体信息智能平台。通过 AI 智能体与可编排工作流的结合，
            实现跨平台信息采集、智能分析、攻略规划、简报生成与信息对比等能力。
          </p>
        </div>
      </div>

      {/* Capabilities grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        {[
          { icon: 'travel_explore', label: '深度分析', desc: '对指定话题进行多维度深度采集与分析，输出结构化报告。' },
          { icon: 'notifications_active', label: '扫描预警', desc: '全网扫描指定关键词，自动筛选高价值信息并推送。' },
          { icon: 'map', label: '攻略规划', desc: '跨平台采集攻略信息，生成行程计划与预算估算。' },
          { icon: 'summarize', label: '简报摘要', desc: '定时汇总多渠道信息，自动生成每日/每周简报。' },
        ].map((cap) => (
          <div key={cap.label} className="glass-slab rounded-xl p-6">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center mb-4" style={{ background: 'oklch(0.78 0.16 85 / 0.1)' }}>
              <span className="material-symbols-outlined" style={{ color: 'var(--primary-gold)' }}>{cap.icon}</span>
            </div>
            <h3 className="serif-headline text-base font-semibold mb-2" style={{ color: 'var(--on-surface)' }}>{cap.label}</h3>
            <p className="text-sm leading-relaxed" style={{ color: 'var(--on-surface-variant)' }}>{cap.desc}</p>
          </div>
        ))}
      </div>

      {/* Status row */}
      <div className="glass-slab rounded-2xl p-8">
        <h3 className="label-caps text-[11px] tracking-[0.2em] font-bold mb-6" style={{ color: 'var(--primary-gold)' }}>系统状态</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <p className="label-caps text-[10px]" style={{ color: 'var(--on-surface-variant)' }}>后端服务</p>
            <div className="flex items-center gap-2 mt-2">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-sm font-semibold" style={{ color: 'var(--on-surface)' }}>运行中</span>
            </div>
          </div>
          <div>
            <p className="label-caps text-[10px]" style={{ color: 'var(--on-surface-variant)' }}>调度器</p>
            <div className="flex items-center gap-2 mt-2">
              <span className={`w-2 h-2 rounded-full ${schedStatus?.active ? 'bg-emerald-500' : 'bg-gray-300'}`} />
              <span className="text-sm font-semibold" style={{ color: 'var(--on-surface)' }}>{schedStatus?.active ? '运行中' : '已停止'}</span>
            </div>
          </div>
          <div>
            <p className="label-caps text-[10px]" style={{ color: 'var(--on-surface-variant)' }}>前端版本</p>
            <p className="text-sm font-semibold mt-2" style={{ color: 'var(--on-surface)' }}>v{pkg.version}</p>
          </div>
          <div>
            <p className="label-caps text-[10px]" style={{ color: 'var(--on-surface-variant)' }}>技术栈</p>
            <p className="text-sm font-semibold mt-2" style={{ color: 'var(--on-surface)' }}>FastAPI · Next.js · LangGraph</p>
          </div>
        </div>
      </div>

      {/* Architecture diagram text */}
      <div className="glass-slab rounded-2xl p-8">
        <h3 className="label-caps text-[11px] tracking-[0.2em] font-bold mb-4" style={{ color: 'var(--primary-gold)' }}>架构概览</h3>
        <div className="flex flex-wrap items-center gap-2 text-sm" style={{ color: 'var(--on-surface-variant)' }}>
          <span className="px-3 py-1 rounded-full bg-[oklch(0.78_0.16_85/0.1)] text-xs font-semibold" style={{ color: 'var(--on-surface)' }}>AI Agent</span>
          <span className="material-symbols-outlined text-sm">arrow_forward</span>
          <span className="px-3 py-1 rounded-full bg-[oklch(0.78_0.16_85/0.1)] text-xs font-semibold" style={{ color: 'var(--on-surface)' }}>工具函数</span>
          <span className="material-symbols-outlined text-sm">arrow_forward</span>
          <span className="px-3 py-1 rounded-full bg-[oklch(0.78_0.16_85/0.1)] text-xs font-semibold" style={{ color: 'var(--on-surface)' }}>爬虫</span>
          <span className="material-symbols-outlined text-sm">arrow_forward</span>
          <span className="px-3 py-1 rounded-full bg-[oklch(0.78_0.16_85/0.1)] text-xs font-semibold" style={{ color: 'var(--on-surface)' }}>分析引擎</span>
          <span className="material-symbols-outlined text-sm">arrow_forward</span>
          <span className="px-3 py-1 rounded-full bg-[oklch(0.78_0.16_85/0.1)] text-xs font-semibold" style={{ color: 'var(--on-surface)' }}>工作流</span>
          <span className="material-symbols-outlined text-sm">arrow_forward</span>
          <span className="px-3 py-1 rounded-full bg-[oklch(0.78_0.16_85/0.1)] text-xs font-semibold" style={{ color: 'var(--on-surface)' }}>结果输出</span>
        </div>
      </div>
    </div>
  );
}
