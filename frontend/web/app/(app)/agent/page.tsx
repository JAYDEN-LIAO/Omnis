'use client';

import { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { useAgentStream } from '@/components/chat/useAgentStream';
import { MessageStream } from '@/components/chat/MessageStream';
import { RightDashboard } from '@/components/chat/RightDashboard';
import { authApi, agentApi, type AgentSession } from '@/lib/api';
import type { AssistantMessage } from '@/components/chat/sse-types';
import { isGuest } from '@/lib/auth-client';

type UIMessage =
  | { kind: 'user'; content: string }
  | { kind: 'assistant'; data: AssistantMessage };

const GREETINGS = [
  // Omnis 身份核心
  'Omnis 已就绪', '我是 Omnis', 'Omnis 随时待命',
  'Omnis 为你服务', '你的 AI 管家 Omnis', 'Omnis 已上线',
  'Omnis 待命中', '欢迎使用 Omnis', 'Omnis 在此',
  // 英文问候
  'Greetings', 'Hello', 'Hey',
  "What's on your mind", 'Welcome back',
  'Good to see you', 'Ready when you are',
  'How can I help', 'Glad you\'re here',
  // 混合风格
  'Omnis at your service', 'Hi there',
  'Long time no see', 'What can Omnis do for you',
];

const SUB_TITLES = [
  // 系统正常运行
  '系统运行正常，全网舆情数据持续更新中。有什么需要关注的？',
  'Omnis 正在监控各大平台，随时为你报告最新动态。',
  '所有通道就绪，舆情数据实时入库。今天想分析什么？',
  '雷达平稳运行，信息流持续汇聚。需要深入了解什么？',
  'Omnis 全链路正常，覆盖微博、抖音、知乎、B站等平台。',
  '监控系统在线，数据持续更新。有什么需要调查的？',
  '扫描引擎待命中，数据仓库已就绪。请告诉我你的关注方向。',
  '多平台数据正在同步，舆情态势实时更新。有什么想了解的？',
  'Omnis 已连接所有数据源，随时可以启动深度分析。',
  '系统健康运行中，历史数据可供回溯分析。需要查什么？',
  '全网监控已启动，最新资讯持续入库。你的关注点是什么？',
  '舆情雷达正常运转，24小时不间断监测中。',
  '信息采集系统运行中，已覆盖主要社交媒体平台。',
  '数据流水线畅通，分析引擎就绪。今天重点关注什么？',
  // v2.0 能力变体
  'Phase Plan 规划引擎已就绪，支持约束提取与多步骤工作流。需要规划什么？',
  '12+ 原子工具 + 4 个组合工具已加载，支持深度话题分析和攻略规划。',
  '支持用户自定义工作流和 cron 定时调度，自然语言描述即可创建。',
  '攻略查询引擎就绪，支持跨平台加权观点对比和行程计划生成。',
  '组合工具已载入：深度分析、扫描预警、攻略规划、简报生成一键执行。',
  // 管家身份变体
  'Omnis 已掌握全平台动态，随时听候差遣。今天想分析什么？',
  '所有能力已就绪，从舆情分析到攻略规划，一句话即可启动。',
  '监控系统后台运行中，无需操心。需要我帮你做什么？',
  '24 小时在线，支持深度分析、工作流调度、定时任务。请随时吩咐。',
  '数据持续更新中，Omnis 替你盯着。你 focus 在决策上就好。',
  '原子工具 + 组合工作流已加载，要跑一次深度分析还是查攻略？',
  'Phase Plan 规划引擎已就绪，复杂任务交给你，拆解步骤交给我。',
  '全平台数据流畅通，想查什么直接说，不用自己翻各平台。',
  '订阅监控自动运行中，Omnis 会主动汇报异常。安心做你的事。',
  '工作流引擎待命中，任何周期性任务都可以用自然语言创建。',
  '从采集到分析到推送，Omnis 全链路可编排。今天想自动化什么？',
  '除了盯舆情，我还能帮你查攻略、做对比、生成简报。试试看？',
  '定时任务、模板匹配、约束规划都已准备就绪。随时可以启动。',
  '跨平台加权对比引擎已加载，需要比较什么产品或目的地？',
  'Omnis 不只是监控工具，更是你的策略助手。想知道什么？',
];

const WELCOME_PILLS = [
  { icon: 'travel_explore', label: '全网舆情分析', prompt: '分析当前全网舆情态势，包括情感趋势、热门话题和风险概览' },
  { icon: 'psychology', label: '深度话题分析', prompt: '对某个话题做深度分析：采集帖子、过滤、聚类、提取槽位、加权对比，输出结构化报告' },
  { icon: 'map', label: '攻略查询规划', prompt: '查询某个目的地的攻略：搜索帖子、过滤攻略内容、聚类、提取槽位、生成行程计划和预算估算' },
  { icon: 'bookmark_manager', label: '订阅管理中心', prompt: '查看和管理我的监控订阅，包括关键词、人物、事件和竞品订阅' },
  { icon: 'account_tree', label: '工作流管理', prompt: '查看我的工作流列表，管理定时任务，查看预设组合工具' },
  { icon: 'notifications_active', label: '风险监控预警', prompt: '查看当前的舆情风险预警列表和高风险话题' },
];

export default function AgentPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [history, setHistory] = useState<UIMessage[]>([]);
  const [input, setInput] = useState('');
  const [pendingSessions, setPendingSessions] = useState<AgentSession[]>([]);
  const [greeting, setGreeting] = useState('');
  const [subtitle, setSubtitle] = useState('');
  const [greetingAnimKey, setGreetingAnimKey] = useState(0);
  const initialSent = useRef(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pendingSessionsRef = useRef<AgentSession[]>([]);

  // 招呼语初始化 + 刷新（每次新对话重新随机选取）
  const refreshGreeting = useCallback(() => {
    setGreeting(GREETINGS[Math.floor(Math.random() * GREETINGS.length)]);
    setSubtitle(SUB_TITLES[Math.floor(Math.random() * SUB_TITLES.length)]);
    setGreetingAnimKey((k) => k + 1);
  }, []);

  useEffect(() => {
    refreshGreeting();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 保持 ref 与 state 同步（避免闭包过期问题）
  useEffect(() => {
    pendingSessionsRef.current = pendingSessions;
  }, [pendingSessions]);

  const { assistant, isStreaming, error, send, cancel, reset } = useAgentStream();

  const { data: user } = useQuery({
    queryKey: ['current-user'],
    queryFn: () => authApi.me(),
  });

  const { data: sessionsData, refetch: refetchSessions } = useQuery({
    queryKey: ['agent-sessions'],
    queryFn: () => agentApi.memory(),
    refetchInterval: 15_000,
  });

  const backendSessions = sessionsData?.data?.sessions ?? [];

  const allSessions = useMemo(() => {
    const pending = pendingSessions.filter(
      (p) => !backendSessions.some((b: AgentSession) => b.session_id === p.session_id),
    );
    return [...pending, ...backendSessions];
  }, [backendSessions, pendingSessions]);

  const handleSelectSession = async (sid: string) => {
    reset();
    setSessionId(sid);
    setHistory([]);

    // 加载该 session 的历史聊天消息
    try {
      const res = await agentApi.messages(sid);
      const msgs = res?.data?.messages;
      if (msgs && msgs.length > 0) {
        const restored: UIMessage[] = msgs.map((m) =>
          m.role === 'user'
            ? { kind: 'user' as const, content: m.content }
            : {
                kind: 'assistant' as const,
                data: {
                  role: 'assistant',
                  text: m.content,
                  toolCalls: [],
                  cards: [],
                  done: true,
                },
              },
        );
        setHistory(restored);
      }
    } catch {
      // 静默失败，用户看到的是空对话
    }
  };

  const handleDeleteSession = async (sid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('确定删除该对话？')) return;
    try {
      const res = await agentApi.deleteSession(sid);
      if (res.success) {
        refetchSessions();
        if (sessionId === sid) { reset(); setSessionId(null); setHistory([]); }
      }
    } catch {}
  };

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [history, assistant?.text, assistant?.toolCalls.length, assistant?.cards.length]);

  useEffect(() => {
    if (assistant?.done && !isStreaming) {
      setHistory((h) => {
        const last = h[h.length - 1];
        if (last && last.kind === 'assistant' && last.data === assistant) return h;
        return [...h, { kind: 'assistant', data: assistant }];
      });
    }
  }, [assistant?.done, isStreaming]);

  const sendMessage = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming || isGuestUser) return;

    setHistory((h) => [...h, { kind: 'user', content: trimmed }]);
    setInput('');

    const flatMessages = [
      ...history.flatMap<{ role: 'user' | 'assistant'; content: string }>((m) =>
        m.kind === 'user'
          ? [{ role: 'user' as const, content: m.content }]
          : m.data.text
            ? [{ role: 'assistant' as const, content: m.data.text }]
            : [],
      ),
      { role: 'user' as const, content: trimmed },
    ];

    await send(flatMessages, {
      sessionId,
      onSessionId: (sid) => setSessionId(sid),
    });
  };

  // 来自工作台预设工作流的自动触发（必须放在 sendMessage 定义之后）
  useEffect(() => {
    const q = searchParams.get('q');
    if (q && !initialSent.current) {
      initialSent.current = true;
      const timer = setTimeout(() => {
        sendMessage(q);
      }, 600);
      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, sendMessage]);

  const isGuestUser = isGuest();

  const startNewSession = () => {
    // 1) 当前已是空对话 — 只刷新招呼语，不重复创建
    if (history.length === 0 && sessionId) {
      refreshGreeting();
      return;
    }

    // 2) 检查是否已有未使用的空 session（避免无限堆叠）
    const existingEmpty = pendingSessionsRef.current.find(
      (p) => !backendSessions.some((b: AgentSession) => b.session_id === p.session_id)
    );
    if (existingEmpty) {
      setSessionId(existingEmpty.session_id);
      setHistory([]);
      reset();
      refreshGreeting();
      return;
    }

    // 3) 创建全新 session
    reset();
    const newId = crypto.randomUUID();
    setSessionId(newId);
    setHistory([]);
    setPendingSessions((prev) => {
      if (prev.some((s) => s.session_id === newId)) return prev;
      return [{ session_id: newId, title: '新对话' }, ...prev];
    });
    refreshGreeting();
  };

  return (
    <div className="h-[calc(100vh-64px)] -m-6 md:-m-8 relative overflow-hidden flex">
      {/* Chat list panel */}
      <div className="w-[220px] shrink-0 flex flex-col pt-3">
        {/* New Chat button */}
        <div className="px-3 mb-2">
          <button
            onClick={startNewSession}
            disabled={isGuestUser}
            className="flex items-center gap-1.5 text-xs transition-all hover:opacity-70"
            style={{ color: 'var(--on-surface-variant)', opacity: isGuestUser ? 0.4 : 1 }}
          >
            <span className="material-symbols-outlined text-base">add</span>
            <span className="label-caps text-[10px] tracking-wider font-medium">新对话</span>
          </button>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto px-3 space-y-0.5 scrollbar-hide">
          {allSessions.length > 0 ? (
            allSessions.map((s) => (
              <div key={s.session_id} className="group flex items-center">
                <button
                  onClick={() => handleSelectSession(s.session_id)}
                  className="flex-1 text-left py-1.5 transition-all text-xs truncate"
                  style={{
                    color: sessionId === s.session_id ? 'var(--primary-gold)' : 'var(--on-surface-faint)',
                  }}
                >
                  {s.title || '新对话'}
                </button>
                <button
                  onClick={(e) => handleDeleteSession(s.session_id, e)}
                  className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded hover:bg-black/5"
                  style={{ color: 'var(--on-surface-faint)' }}
                  title="删除对话"
                >
                  <span className="material-symbols-outlined text-[14px]">close</span>
                </button>
              </div>
            ))
          ) : (
            <div className="py-6 text-center text-xs" style={{ color: 'var(--on-surface-faint)' }}>
              暂无历史对话
            </div>
          )}
        </div>

        {/* Bottom count */}
        <div className="px-3 py-2">
          <span className="text-[9px] label-caps" style={{ color: 'var(--on-surface-faint)' }}>
            {allSessions.length} 个对话
          </span>
        </div>
      </div>

      <div className="flex-1 flex flex-col min-w-0 mr-[316px]">
        <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-hide px-8 py-4 space-y-12 pb-32">
          {/* Welcome greeting — 始终在顶部，副标题+功能按钮永久显示 */}
          <section className="max-w-3xl mx-auto pt-12">
            <AnimatePresence mode="wait">
              <motion.div
                key={greetingAnimKey}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -14 }}
                transition={{ duration: 0.25, ease: 'easeOut' }}
              >
                <h3 className="serif-headline text-4xl lg:text-5xl text-[color:var(--on-surface)] mb-6 opacity-95">
                  {greeting}, {user?.nickname || 'Analyst'}.
                </h3>
                <p className="text-lg text-[color:var(--on-surface-variant)] mb-8 max-w-xl">
                  {subtitle}
                </p>
              </motion.div>
            </AnimatePresence>
            <div className="flex flex-wrap gap-2">
              {WELCOME_PILLS.map((pill) => (
                <button
                  key={pill.label}
                  type="button"
                  disabled={isGuestUser}
                  onClick={() => { if (!isGuestUser) { setInput(pill.prompt); inputRef.current?.focus(); } }}
                  className="px-4 py-2 rounded-full caustic-card text-sm text-[color:var(--on-surface-variant)] hover:text-[color:var(--primary-gold)] hover:border-[color:var(--primary-gold)]/30 transition-all flex items-center gap-1.5"
                  style={{ opacity: isGuestUser ? 0.5 : 1, cursor: isGuestUser ? 'not-allowed' : 'pointer' }}
                >
                  <span className="material-symbols-outlined text-base">{pill.icon}</span>
                  {pill.label}
                </button>
              ))}
            </div>
          </section>

          {/* Chat messages — 追加在 welcome 下方 */}
          <div className="max-w-3xl mx-auto space-y-10">
            {history.map((m, i) => {
              if (m.kind === 'user') {
                return (
                  <div key={`u-${i}`} className="flex flex-col items-end">
                    <div className="flex items-center gap-3 mb-2 opacity-50 flex-row-reverse">
                      <span className="text-[10px] label-caps tracking-tighter" style={{ color: 'var(--on-surface-variant)' }}>{user?.nickname || 'User'}</span>
                      <div className="h-[0.5px] flex-1 bg-gradient-to-l from-on-surface-faint/20 to-transparent" />
                    </div>
                    <p className="text-sm text-right leading-relaxed" style={{ color: 'var(--on-surface-variant)' }}>{m.content}</p>
                  </div>
                );
              }
              return (
                <div key={`a-${i}`} className="space-y-6">
                  <div className="flex items-center gap-3 opacity-80">
                    <span className="text-[10px] label-caps tracking-tighter" style={{ color: 'var(--primary-gold)' }}>Omnis</span>
                    <div className="h-[0.5px] flex-1 bg-gradient-to-r from-primary/30 to-transparent" />
                  </div>
                  <MessageStream message={m.data} streaming={false} onAction={(text) => { setInput(text); inputRef.current?.focus(); }} />
                </div>
              );
            })}

            {/* Current streaming assistant */}
            {assistant && !assistant.done && (
              <div className="space-y-6">
                <div className="flex items-center gap-3 opacity-80">
                  <span className="text-[10px] label-caps tracking-tighter" style={{ color: 'var(--primary-gold)' }}>Omnis</span>
                  <div className="h-[0.5px] flex-1 bg-gradient-to-r from-primary/30 to-transparent" />
                </div>
                <MessageStream message={assistant} streaming={true} />
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="flex items-start gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: 'rgba(220, 38, 38, 0.08)', color: '#dc2626' }}>
                <span className="material-symbols-outlined text-sm shrink-0 mt-0.5">warning</span>
                <span>{error}</span>
              </div>
            )}
          </div>
        </div>

        {/* Input bar — capsule at bottom center */}
        <div className="shrink-0 px-8 pb-6 pt-2">
          <div className="max-w-3xl mx-auto">
            <form
              onSubmit={(e) => { e.preventDefault(); sendMessage(input); }}
              className="glass-slab rounded-[2rem] p-2 flex items-center gap-3"
            >
              {isGuestUser ? (
                <div className="flex-1 flex items-center gap-2 ml-2 py-2">
                  <span className="text-sm" style={{ color: 'var(--on-surface-variant)' }}>请</span>
                  <button
                    type="button"
                    onClick={() => router.push('/login')}
                    className="font-semibold underline-offset-2 hover:underline text-sm"
                    style={{ color: 'var(--primary-gold)' }}
                  >
                    登录
                  </button>
                  <span className="text-sm" style={{ color: 'var(--on-surface-variant)' }}>后使用 Omnis</span>
                </div>
              ) : (
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage(input);
                    }
                  }}
                  placeholder="向 Omnis 提问：舆情分析、风险查询、全网搜索..."
                  rows={1}
                  className="flex-1 bg-transparent border-none outline-none text-sm resize-none py-2 scrollbar-hide max-h-32 ml-2"
                  style={{ color: 'var(--on-surface)' }}
                  onInput={(e) => {
                    const el = e.currentTarget;
                    el.style.height = 'auto';
                    el.style.height = `${el.scrollHeight}px`;
                  }}
                />
              )}
              {isStreaming ? (
                <button
                  type="button"
                  onClick={cancel}
                  className="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
                  style={{ background: 'rgba(0,0,0,0.05)', color: 'var(--on-surface-variant)' }}
                >
                  <span className="material-symbols-outlined text-xl">close</span>
                </button>
              ) : !isGuestUser ? (
                <button
                  type="submit"
                  disabled={!input.trim()}
                  className="w-10 h-10 rounded-full brushed-gold flex items-center justify-center shrink-0 disabled:opacity-40"
                  style={{ color: 'oklch(0.2 0.05 85)' }}
                >
                  <span className="material-symbols-outlined text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>auto_awesome</span>
                </button>
              ) : null}
            </form>
          </div>
        </div>
      </div>

      {/* Fixed right panel — Intelligence Live */}
      <aside className="fixed right-4 top-20 bottom-4 w-[300px] rounded-xl glass-slab flex flex-col z-0 overflow-hidden">
        <RightDashboard onQuickAction={sendMessage} />
      </aside>
    </div>
  );
}
