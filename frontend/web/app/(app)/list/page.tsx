'use client';

import { useMemo, useState, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { Skeleton } from '@/components/ui/skeleton';
import { radarApi, type TopicListItem } from '@/lib/api';

const riskBadge: Record<string, string> = {
  高风险: 'risk-high',
  中风险: 'risk-medium',
  低风险: 'risk-stable',
  待观察: 'risk-stable',
};

const riskTextMap: Record<string, string> = {
  高风险: '高风险',
  中风险: '中风险',
  低风险: '低风险',
  待观察: '待观察',
};

export default function ListPage() {
  const [globalFilter, setGlobalFilter] = useState('');
  const [platformFilter, setPlatformFilter] = useState<string>('all');
  const [sorting, setSorting] = useState<SortingState>([]);

  const { data, isLoading } = useQuery({
    queryKey: ['topic-list', platformFilter],
    queryFn: () => radarApi.topicList({ platform: platformFilter === 'all' ? undefined : platformFilter }),
    refetchInterval: 10_000,
  });

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: () => radarApi.settings(),
    refetchInterval: 30_000,
  });

  const { data: radarStatus } = useQuery({
    queryKey: ['radar-status'],
    queryFn: () => radarApi.status(),
    refetchInterval: 10_000,
  });

  const columns = useMemo<ColumnDef<TopicListItem>[]>(
    () => [
      {
        accessorKey: 'topic_name',
        header: '信号详情',
        cell: ({ row }) => {
          const risk = row.original.risk_text;
          const isHigh = risk === '高风险';
          const isMed = risk === '中风险';
          const iconBoxBg = isHigh
            ? 'oklch(0.96 0.02 25)'
            : isMed
              ? 'oklch(0.78 0.16 85 / 0.12)'
              : 'oklch(0.95 0.03 155)';
          const iconColor = isHigh
            ? 'var(--status-error)'
            : isMed
              ? 'var(--primary-gold)'
              : '#10b981';
          const iconBorder = isHigh
            ? 'var(--status-error)'
            : isMed
              ? 'var(--primary-gold)'
              : '#10b981';
          return (
            <div className="flex gap-4">
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0 border"
                style={{ background: iconBoxBg, borderColor: `color-mix(in srgb, ${iconBorder} 20%, transparent)` }}
              >
                <span className="material-symbols-outlined" style={{ color: iconColor }}>
                  {isHigh ? 'memory' : isMed ? 'bolt' : 'language'}
                </span>
              </div>
              <div className="min-w-0">
                <h3 className="serif-headline text-base mb-1 leading-tight truncate" style={{ color: 'var(--on-surface)' }}>
                  {row.original.topic_name}
                </h3>
                <p className="text-sm line-clamp-2 max-w-md" style={{ color: 'var(--on-surface-variant)' }}>
                  {row.original.cluster_summary || row.original.core_issue || ''}
                </p>
              </div>
            </div>
          );
        },
      },
      {
        accessorKey: 'keyword',
        header: '关键词',
        cell: ({ getValue }) => (
          <span className="px-3 py-1 rounded-full label-caps text-[10px]" style={{ background: 'var(--bg-inner)', color: 'var(--on-surface-variant)' }}>
            {String(getValue())}
          </span>
        ),
      },
      {
        id: 'platforms',
        header: () => {
          const [open, setOpen] = useState(false);
          return (
            <div className="relative">
              <button
                onClick={() => setOpen(!open)}
                className="flex items-center gap-1 hover:opacity-80"
              >
                来源
                <span className="material-symbols-outlined text-sm" style={{ opacity: 0.5 }}>expand_more</span>
              </button>
              {open && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
                  <div
                    className="absolute left-0 top-full mt-1 z-20 w-40 rounded-xl border shadow-lg overflow-hidden"
                    style={{ background: 'white', borderColor: 'var(--border-faint)' }}
                  >
                    <button
                      onClick={() => { setPlatformFilter('all'); setOpen(false); }}
                      className="w-full text-left px-4 py-2.5 text-sm transition-colors hover:bg-[oklch(0.78_0.16_85/0.08)]"
                      style={{
                        color: platformFilter === 'all' ? 'var(--primary-gold)' : 'var(--on-surface)',
                        fontWeight: platformFilter === 'all' ? 600 : 400,
                      }}
                    >
                      全部来源
                    </button>
                    {allPlatforms.map((p) => (
                      <button
                        key={p}
                        onClick={() => { setPlatformFilter(p); setOpen(false); }}
                        className="w-full text-left px-4 py-2.5 text-sm transition-colors hover:bg-[oklch(0.78_0.16_85/0.08)]"
                        style={{
                          color: platformFilter === p ? 'var(--primary-gold)' : 'var(--on-surface)',
                          fontWeight: platformFilter === p ? 600 : 400,
                        }}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          );
        },
        cell: ({ row }) => {
          const platforms = row.original.platforms;
          if (!platforms || platforms.length === 0) return <span className="text-xs text-[color:var(--on-surface-faint)]">&mdash;</span>;
          const display = platforms.length > 2 ? platforms.slice(0, 2) : platforms;
          const extra = platforms.length > 2 ? platforms.length - 2 : 0;
          return (
            <div className="flex flex-wrap items-center gap-1.5 max-w-[180px]">
              {display.map((p) => (
                <button
                  key={p}
                  onClick={() => setPlatformFilter(platformFilter === p ? 'all' : p)}
                  className="px-2 py-0.5 rounded label-caps text-[9px] transition-all hover:opacity-70 cursor-pointer"
                  style={{
                    background: platformFilter === p ? 'oklch(0.78 0.16 85 / 0.15)' : 'var(--bg-inner)',
                    color: platformFilter === p ? 'var(--primary-gold)' : 'var(--on-surface-variant)',
                  }}
                >
                  {p}
                </button>
              ))}
              {extra > 0 && (
                <span className="text-[9px] label-caps" style={{ color: 'var(--on-surface-faint)' }}>+{extra}</span>
              )}
            </div>
          );
        },
      },
      {
        id: 'risk',
        header: '风险等级',
        cell: ({ row }) => {
          const risk = row.original.risk_text;
          const cls = riskBadge[risk] || 'risk-stable';
          const label = riskTextMap[risk] || risk;
          const dotColor = risk === '高风险' ? 'var(--status-error)' : risk === '中风险' ? 'var(--primary-gold)' : '#10b981';
          return (
            <div className={`inline-flex items-center px-4 py-1.5 rounded-full label-caps text-[10px] font-bold ${cls}`}>
              <span className="w-1.5 h-1.5 rounded-full mr-2" style={{ background: dotColor }} />
              {label}
            </div>
          );
        },
      },
      {
        accessorKey: 'sentiment',
        header: '情感',
        cell: ({ getValue }) => {
          const v = String(getValue());
          const icon = v === '负面' || v === 'negative' ? 'trending_down'
            : v === '正面' || v === 'positive' ? 'trending_up'
            : 'trending_flat';
          const color = v === '负面' || v === 'negative' ? 'var(--status-error)'
            : v === '正面' || v === 'positive' ? '#10b981'
            : 'var(--on-surface-variant)';
          return (
            <div className="flex justify-center">
              <span className="material-symbols-outlined" style={{ color }}>{icon}</span>
            </div>
          );
        },
      },
      {
        accessorKey: 'last_seen',
        header: '时间 (UTC)',
        cell: ({ getValue }) => {
          const v = String(getValue());
          if (!v) return <span className="data-mono text-xs text-[color:var(--on-surface-faint)]">&mdash;</span>;
          const d = new Date(v);
          return (
            <div className="data-mono text-xs text-right" style={{ color: 'var(--on-surface-variant)' }}>
              <div>{d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })}</div>
              <div className="opacity-60">{d.toLocaleTimeString('zh-CN', { hour12: false })}</div>
            </div>
          );
        },
      },
    ],
    [],
  );

  const tableData = useMemo(() => {
    if (!data) return [];
    if (!globalFilter) return data;
    const q = globalFilter.toLowerCase();
    return data.filter(
      (t) =>
        t.topic_name.toLowerCase().includes(q) ||
        t.keyword.toLowerCase().includes(q) ||
        (t.cluster_summary ?? '').toLowerCase().includes(q) ||
        (t.core_issue ?? '').toLowerCase().includes(q),
    );
  }, [data, globalFilter]);

  const table = useReactTable({
    data: tableData,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const containerRef = useRef<HTMLDivElement>(null);
  const rows = table.getRowModel().rows;
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 80,
    overscan: 8,
  });

  const allPlatforms = useMemo(() => {
    if (!data) return [];
    const set = new Set<string>();
    data.forEach((item) => item.platforms?.forEach((p) => set.add(p)));
    return Array.from(set).sort();
  }, [data]);

  return (
    <div className="flex flex-col gap-6 max-w-[1400px] mx-auto">
      {/* Filter bar */}

      {/* Filter bar */}
      <section className="flex flex-wrap items-center gap-4 glass-slab p-4 rounded-xl">
        <div className="relative flex-grow max-w-md">
          <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2" style={{ color: 'var(--on-surface-variant)' }}>search</span>
          <input
            placeholder="搜索关键词..."
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            className="w-full pl-12 pr-4 py-3 bg-white/70 border border-[color:var(--border-faint)] focus:border-[color:var(--primary-gold)] focus:ring-2 focus:ring-[oklch(0.78_0.16_85/0.15)] rounded-lg text-sm transition-all outline-none"
            type="text"
          />
        </div>

      </section>

      {/* Table */}
      <div className="glass-slab rounded-2xl overflow-hidden">
        <div ref={containerRef} className="overflow-auto max-h-[calc(100vh-320px)]">
          <table className="w-full border-collapse">
            <thead className="sticky top-0 z-10 bg-white">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id} className="border-b border-[color:var(--border-faint)]">
                  {hg.headers.map((header) => {
                    const canSort = header.column.getCanSort();
                    const sorted = header.column.getIsSorted();
                    return (
                      <th
                        key={header.id}
                        className={`py-5 px-6 label-caps text-[11px] font-bold text-left ${header.id === 'last_seen' ? 'text-right' : header.id === 'sentiment' ? 'text-center' : ''}`}
                        style={{ color: 'var(--on-surface)', cursor: canSort ? 'pointer' : 'default' }}
                        onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
                      >
                        <span className="inline-flex items-center gap-1">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {canSort && (
                            sorted === 'asc' ? (
                              <span className="material-symbols-outlined text-sm">arrow_upward</span>
                            ) : sorted === 'desc' ? (
                              <span className="material-symbols-outlined text-sm">arrow_downward</span>
                            ) : (
                              <span className="material-symbols-outlined text-sm" style={{ opacity: 0.3 }}>unfold_more</span>
                            )
                          )}
                        </span>
                      </th>
                    );
                  })}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-[color:var(--border-faint)]">
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    {columns.map((_, j) => (
                      <td key={j} className="py-6 px-6">
                        <Skeleton className="h-6 w-full" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={columns.length} className="py-16 text-center text-sm text-[color:var(--on-surface-faint)]">
                    没有匹配的话题
                  </td>
                </tr>
              ) : (
                <>
                  {virtualizer.getVirtualItems().map((virtualRow) => {
                    const row = rows[virtualRow.index];
                    return (
                      <tr
                        key={row.id}
                        className="row-hover-effect transition-all duration-200"
                        style={{ height: virtualRow.size }}
                      >
                        {row.getVisibleCells().map((cell) => (
                          <td
                            key={cell.id}
                            className="py-6 px-6 align-middle"
                            style={{ color: 'var(--on-surface-variant)' }}
                          >
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination footer */}
        <div className="py-5 px-6 flex items-center justify-between border-t border-[color:var(--border-faint)]" style={{ background: 'rgba(255,255,255,0.3)' }}>
          <span className="label-caps text-[10px]" style={{ color: 'var(--on-surface-variant)' }}>
            显示第 1 到 {Math.min(tableData.length, 50)} 条，共 {tableData.length} 条信号
          </span>
        </div>
      </div>

      {/* System status footer */}
      <footer className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-2">
        <div className="glass-slab p-6 rounded-xl flex items-center gap-4">
          <div className="w-10 h-10 rounded-full bg-[oklch(0.78_0.16_85/0.12)] flex items-center justify-center">
            <span className="material-symbols-outlined text-[color:var(--primary-gold)]">manage_search</span>
          </div>
          <div>
            <p className="label-caps text-[10px]" style={{ color: 'var(--on-surface-variant)' }}>监控关键词</p>
            <p className="serif-headline text-lg" style={{ color: 'var(--on-surface)' }}>{settings?.keywords?.length ?? '—'} 个</p>
          </div>
        </div>
        <div className="glass-slab p-6 rounded-xl flex items-center gap-4">
          <div className="w-10 h-10 rounded-full bg-[oklch(0.78_0.16_85/0.12)] flex items-center justify-center">
            <span className="material-symbols-outlined text-[color:var(--primary-gold)]">sensors</span>
          </div>
          <div>
            <p className="label-caps text-[10px]" style={{ color: 'var(--on-surface-variant)' }}>监控平台</p>
            <p className="serif-headline text-lg" style={{ color: 'var(--on-surface)' }}>{settings?.platforms?.length ?? '—'} 个平台</p>
          </div>
        </div>
        <div className="glass-slab p-6 rounded-xl flex items-center gap-4">
          <div className="w-10 h-10 rounded-full bg-[oklch(0.78_0.16_85/0.12)] flex items-center justify-center">
            <span className="material-symbols-outlined text-[color:var(--primary-gold)]">update</span>
          </div>
          <div>
            <p className="label-caps text-[10px]" style={{ color: 'var(--on-surface-variant)' }}>最后同步</p>
            <p className="serif-headline text-lg" style={{ color: 'var(--on-surface)' }}>
              {radarStatus?.last_run_time
                ? new Date(radarStatus.last_run_time).toLocaleTimeString('zh-CN', { hour12: false })
                : radarStatus?.is_running
                  ? '扫描中...'
                  : '—'}
            </p>
          </div>
        </div>
      </footer>

    </div>
  );
}
