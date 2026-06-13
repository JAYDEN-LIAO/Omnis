'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ToolCallChip } from './ToolCallChip';
import { renderCard } from './cards/registry';
import type { AssistantMessage, SearchStreamItem } from './sse-types';

interface Props {
  message: AssistantMessage;
  streaming?: boolean;
  onAction?: (text: string) => void;
}

export function MessageStream({ message, streaming = false, onAction }: Props) {
  const hasText = message.text.length > 0;
  const hasTools = message.toolCalls.length > 0;
  const hasCards = message.cards.length > 0;
  const hasProgressItems = message.progressItems && message.progressItems.length > 0;
  const showCursor = streaming && !message.done;

  // 从 tool_cards 中提取搜索词（search_stream 卡片的数据里有 query）
  const searchQuery = message.cards.find(c => c.ui.type === 'search_stream')?.data
    ? (message.cards.find(c => c.ui.type === 'search_stream')!.data as Record<string, unknown>)?.query as string | undefined
    : undefined;
  // 也用 progressItems 的第一个来获取 query（工具还没结束时用）
  const effectiveQuery = searchQuery || (hasProgressItems ? '当前搜索' : '');

  return (
    <div className="min-w-0 max-w-[80%]">
      {/* Text — rendered markdown */}
      {hasText && (
        <div className="text-base leading-relaxed" style={{ color: 'var(--on-surface)' }}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              strong: ({ children }) => <strong className="font-semibold" style={{ color: 'var(--on-surface)' }}>{children}</strong>,
              em: ({ children }) => <em style={{ fontStyle: 'italic' }}>{children}</em>,
              code: ({ children }) => (
                <code className="px-1 py-0.5 rounded text-sm font-mono" style={{ background: 'oklch(0.93 0.005 260)', color: 'var(--on-surface)' }}>{children}</code>
              ),
              p: ({ children }) => <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>,
              ul: ({ children }) => <ul className="mb-3 list-disc pl-5 space-y-1">{children}</ul>,
              ol: ({ children }) => <ol className="mb-3 list-decimal pl-5 space-y-1">{children}</ol>,
              li: ({ children }) => <li className="leading-relaxed">{children}</li>,
              h1: ({ children }) => <h1 className="text-xl font-bold mb-3 mt-4" style={{ color: 'var(--on-surface)' }}>{children}</h1>,
              h2: ({ children }) => <h2 className="text-lg font-bold mb-2 mt-3" style={{ color: 'var(--on-surface)' }}>{children}</h2>,
              h3: ({ children }) => <h3 className="text-base font-bold mb-2 mt-3" style={{ color: 'var(--on-surface)' }}>{children}</h3>,
              a: ({ children, href }) => (
                <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--primary-gold)' }} className="underline underline-offset-2">
                  {children}
                </a>
              ),
            }}
          >
            {message.text}
          </ReactMarkdown>
          {showCursor && <span className="ai-cursor" />}
        </div>
      )}
      {!hasText && showCursor && (
        <div className="text-base" style={{ color: 'var(--on-surface)' }}>
          <span className="ai-cursor" />
        </div>
      )}

      {/* Tool call chips */}
      {hasTools && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {message.toolCalls.map((tc) => (
            <ToolCallChip key={tc.call_id} block={tc} />
          ))}
        </div>
      )}

      {/* Glass-slab cards embedded in response */}
      {hasCards && (
        <div className="mt-4">
          {message.cards.map((c) => (
            <div key={c.key}>{renderCard(c)}</div>
          ))}
        </div>
      )}

      {/* 实时搜索结果（tool_progress 阶段，tool_result 之前） */}
      {!hasCards && hasProgressItems && (
        <div className="mt-4">
          <LiveSearchResults items={message.progressItems!} streaming={streaming} />
        </div>
      )}

      {/* 搜索结果操作按钮 */}
      {(hasCards || (!streaming && hasProgressItems)) && effectiveQuery && onAction && (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onAction(`将"${effectiveQuery}"添加为监控关键词`)}
            className="px-3.5 py-1.5 rounded-full caustic-card text-xs text-[var(--on-surface-variant)] hover:text-[var(--primary-gold)] hover:border-[var(--primary-gold)]/30 transition-all flex items-center gap-1.5"
          >
            <span className="material-symbols-outlined text-base">add_circle</span>
            添加为监控关键词
          </button>
          <button
            type="button"
            onClick={() => onAction(`分析"${effectiveQuery}"的搜索结果的详细内容`)}
            className="px-3.5 py-1.5 rounded-full caustic-card text-xs text-[var(--on-surface-variant)] hover:text-[var(--primary-gold)] hover:border-[var(--primary-gold)]/30 transition-all flex items-center gap-1.5"
          >
            <span className="material-symbols-outlined text-base">insights</span>
            详细分析
          </button>
          <button
            type="button"
            onClick={() => onAction(`为"${effectiveQuery}"设置预警规则`)}
            className="px-3.5 py-1.5 rounded-full caustic-card text-xs text-[var(--on-surface-variant)] hover:text-[var(--primary-gold)] hover:border-[var(--primary-gold)]/30 transition-all flex items-center gap-1.5"
          >
            <span className="material-symbols-outlined text-base">notifications_active</span>
            设置预警
          </button>
        </div>
      )}

      {/* Error */}
      {message.error && (
        <div className="mt-2 flex items-start gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: 'rgba(220, 38, 38, 0.08)', color: '#dc2626' }}>
          <span className="material-symbols-outlined text-sm shrink-0 mt-0.5">warning</span>
          <span>{message.error}</span>
        </div>
      )}
    </div>
  );
}

/** 实时搜索结果卡片（tool_progress 阶段实时增量） */
function LiveSearchResults({ items, streaming }: { items: SearchStreamItem[]; streaming: boolean }) {
  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{ background: 'var(--bg-inner)', borderColor: 'var(--border-faint)' }}
    >
      <div className="flex items-center gap-2 px-3 py-2 border-b" style={{ borderColor: 'var(--border-faint)' }}>
        <span className="material-symbols-outlined text-sm" style={{ color: 'var(--primary-gold)' }}>search</span>
        <span className="text-xs label-caps font-medium" style={{ color: 'var(--on-surface-variant)' }}>
          实时搜索结果
        </span>
        {streaming && (
          <span className="ml-auto flex items-center gap-1.5 text-[10px]" style={{ color: 'var(--on-surface-faint)' }}>
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" style={{ animation: 'pulse-ring 2s infinite' }} />
            搜集中
          </span>
        )}
        <span className="ml-auto text-[10px]" style={{ color: 'var(--on-surface-faint)' }}>
          {items.length} 条
        </span>
      </div>
      <div className="divide-y" style={{ borderColor: 'var(--border-faint)' }}>
        {items.map((it, i) => (
          <a
            key={i}
            href={it.url || '#'}
            target="_blank"
            rel="noreferrer"
            className="block px-3 py-2 hover:bg-black/5 transition-colors group"
          >
            <div className="flex items-center gap-1.5">
              <span
                className="rounded px-1 py-px text-[9px] font-medium label-caps"
                style={{ background: 'oklch(0.78 0.16 85 / 0.1)', color: 'var(--primary-gold)' }}
              >
                {it.platform || 'web'}
              </span>
              <span className="min-w-0 flex-1 truncate text-xs font-medium group-hover:opacity-70" style={{ color: 'var(--on-surface)' }}>
                {it.title || '无标题'}
              </span>
              <span className="material-symbols-outlined text-sm shrink-0 opacity-0 group-hover:opacity-40" style={{ color: 'var(--on-surface-variant)' }}>
                open_in_new
              </span>
            </div>
            {it.snippet && (
              <p className="mt-0.5 line-clamp-2 text-[11px]" style={{ color: 'var(--on-surface-variant)' }}>
                {it.snippet}
              </p>
            )}
          </a>
        ))}
      </div>
    </div>
  );
}
