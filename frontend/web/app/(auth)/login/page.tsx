'use client';

import { useState, Suspense, useRef, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { authApi } from '@/lib/api';
import { persistAuth } from '@/lib/auth-client';
import { toast } from 'sonner';

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const redirect = params.get('redirect') ?? '/agent';
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [nickname, setNickname] = useState('');
  const [pending, setPending] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const omnisRef = useRef<HTMLHeadingElement>(null);
  const [hubPos, setHubPos] = useState({ x: 185, y: 260 });

  const updateHubPosition = useCallback(() => {
    if (!omnisRef.current) return;
    const el = omnisRef.current;
    const section = el.closest('section');
    if (!section) return;
    const er = el.getBoundingClientRect();
    const sr = section.getBoundingClientRect();
    const vbW = 1000, vbH = 800;
    const scaleX = sr.width / vbW;
    const scaleY = sr.height / vbH;
    const scale = Math.max(scaleX, scaleY);
    const ox = (sr.width - vbW * scale) / 2;
    const oy = (sr.height - vbH * scale) / 2;
    setHubPos({
      x: (er.left + er.width / 2 - sr.left - ox) / scale,
      y: (er.top + er.height / 2 - sr.top - oy) / scale,
    });
  }, []);

  useEffect(() => {
    updateHubPosition();
    window.addEventListener('resize', updateHubPosition);
    return () => window.removeEventListener('resize', updateHubPosition);
  }, [updateHubPosition]);

  const handleEmailAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) { toast.error('邮箱和密码不能为空'); return; }
    setPending('email');
    try {
      const res = mode === 'login'
        ? await authApi.login(email, password)
        : await authApi.register(email, password, nickname || email.split('@')[0]);
      persistAuth(res.token, res.user.role);
      toast.success(mode === 'login' ? '登录成功' : '注册成功');
      router.replace(redirect);
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || (mode === 'login' ? '邮箱或密码错误' : '注册失败，邮箱可能已被使用');
      toast.error(msg);
    } finally {
      setPending(null);
    }
  };

  const handleGuestLogin = async () => {
    setPending('guest');
    try {
      const res = await authApi.guestLogin();
      persistAuth(res.token, 'guest');
      toast.success('游客模式已开启');
      router.replace(redirect);
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message || '游客登录失败';
      toast.error(msg);
    } finally {
      setPending(null);
    }
  };

  const handleGoogleLogin = async () => {
    setPending('google');
    try {
      const base = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8008';
      window.location.href = `${base}/api/auth/oauth/google/login?redirect=${encodeURIComponent(redirect)}`;
    } catch {
      toast.error('登录失败');
      setPending(null);
    }
  };

  return (
    <div className="flex min-h-screen w-full relative overflow-hidden">
      <div className="interlaced-grid" />

      {/* Left 70% — Brand narrative */}
      <section
        className="hidden lg:flex split-70 relative items-start justify-start pt-24 px-16 pb-16 overflow-hidden"
        style={{
          width: '70%',
          background: 'radial-gradient(ellipse 80% 60% at 30% 50%, var(--bg-inner) 0%, var(--bg-outer) 100%)',
        }}
      >
        {/* Ambient background */}
        <div className="absolute inset-0 z-0">
          <div className="absolute -top-[10%] -left-[10%] w-[50%] h-[50%] rounded-full" style={{ background: 'oklch(0.78 0.16 85 / 0.12)', filter: 'blur(120px)' }} />
          <div className="absolute -bottom-[10%] -right-[10%] w-[40%] h-[40%] rounded-full" style={{ background: 'oklch(0.95 0.03 155 / 0.3)', filter: 'blur(100px)' }} />
        </div>

        {/* Platform network graph — hub near Omnis, nodes radiating outward */}
        <div className="absolute inset-0 z-[1] pointer-events-none overflow-hidden">
          <svg
            className="w-full h-full"
            viewBox="0 0 1000 800"
            preserveAspectRatio="xMidYMid slice"
          >
            <g className="network-float" style={{ transformOrigin: `${hubPos.x} ${hubPos.y}` }}>
              {/* Edges — hub mesh (dynamically aligned to Omnis text) */}
              <g className="network-edges" fill="none" stroke="oklch(0.78 0.16 85 / 0.12)" strokeWidth="1.1">
                <line x1={hubPos.x} y1={hubPos.y} x2="45" y2="80" />
                <line x1={hubPos.x} y1={hubPos.y} x2="750" y2="110" />
                <line x1={hubPos.x} y1={hubPos.y} x2="30" y2="390" />
                <line x1={hubPos.x} y1={hubPos.y} x2="880" y2="280" />
                <line x1={hubPos.x} y1={hubPos.y} x2="50" y2="650" />
                <line x1={hubPos.x} y1={hubPos.y} x2="450" y2="730" />
                <line x1={hubPos.x} y1={hubPos.y} x2="780" y2="600" />
                {/* Inter-node connections */}
                <line x1="45" y1="80" x2="30" y2="390" />
                <line x1="750" y1="110" x2="880" y2="280" />
                <line x1="30" y1="390" x2="50" y2="650" />
                <line x1="880" y1="280" x2="780" y2="600" />
                <line x1="50" y1="650" x2="450" y2="730" />
                <line x1="450" y1="730" x2="780" y2="600" />
                <line x1="45" y1="80" x2="750" y2="110" />
                <line x1="30" y1="390" x2="880" y2="280" />
                <line x1="50" y1="650" x2="780" y2="600" />
              </g>

              {/* Edges animated dash flow */}
              <g className="network-edges-flow" fill="none" stroke="oklch(0.78 0.16 85 / 0.06)" strokeWidth="1.3" strokeDasharray="5 14">
                <line x1={hubPos.x} y1={hubPos.y} x2="45" y2="80" className="edge-flow" />
                <line x1={hubPos.x} y1={hubPos.y} x2="750" y2="110" className="edge-flow" />
                <line x1={hubPos.x} y1={hubPos.y} x2="30" y2="390" className="edge-flow" />
                <line x1={hubPos.x} y1={hubPos.y} x2="880" y2="280" className="edge-flow" />
                <line x1={hubPos.x} y1={hubPos.y} x2="50" y2="650" className="edge-flow" />
                <line x1={hubPos.x} y1={hubPos.y} x2="450" y2="730" className="edge-flow" />
                <line x1={hubPos.x} y1={hubPos.y} x2="780" y2="600" className="edge-flow" />
              </g>

              {/* Nodes */}
              {/* 微博 */}
              <g className="network-node">
                <circle cx="45" cy="80" r="5" fill="oklch(0.78 0.16 85 / 0.55)" className="node-pulse" />
                <circle cx="45" cy="80" r="2.5" fill="oklch(0.78 0.16 85 / 0.85)" />
                <text x="56" y="84" fill="oklch(0.78 0.16 85 / 0.4)" fontSize="10" fontFamily="system-ui, sans-serif" letterSpacing="1">微博</text>
              </g>

              {/* 小红书 */}
              <g className="network-node">
                <circle cx="750" cy="110" r="5" fill="oklch(0.78 0.16 85 / 0.55)" className="node-pulse node-delay-1" />
                <circle cx="750" cy="110" r="2.5" fill="oklch(0.78 0.16 85 / 0.85)" />
                <text x="762" y="114" fill="oklch(0.78 0.16 85 / 0.4)" fontSize="10" fontFamily="system-ui, sans-serif" letterSpacing="1">小红书</text>
              </g>

              {/* B站 */}
              <g className="network-node">
                <circle cx="30" cy="390" r="5" fill="oklch(0.78 0.16 85 / 0.55)" className="node-pulse node-delay-2" />
                <circle cx="30" cy="390" r="2.5" fill="oklch(0.78 0.16 85 / 0.85)" />
                <text x="42" y="394" fill="oklch(0.78 0.16 85 / 0.4)" fontSize="10" fontFamily="system-ui, sans-serif" letterSpacing="1">B站</text>
              </g>

              {/* 抖音 */}
              <g className="network-node">
                <circle cx="880" cy="280" r="5" fill="oklch(0.78 0.16 85 / 0.55)" className="node-pulse node-delay-3" />
                <circle cx="880" cy="280" r="2.5" fill="oklch(0.78 0.16 85 / 0.85)" />
                <text x="892" y="284" fill="oklch(0.78 0.16 85 / 0.4)" fontSize="10" fontFamily="system-ui, sans-serif" letterSpacing="1">抖音</text>
              </g>

              {/* 知乎 */}
              <g className="network-node">
                <circle cx="50" cy="650" r="5" fill="oklch(0.78 0.16 85 / 0.55)" className="node-pulse node-delay-4" />
                <circle cx="50" cy="650" r="2.5" fill="oklch(0.78 0.16 85 / 0.85)" />
                <text x="62" y="654" fill="oklch(0.78 0.16 85 / 0.4)" fontSize="10" fontFamily="system-ui, sans-serif" letterSpacing="1">知乎</text>
              </g>

              {/* 快手 */}
              <g className="network-node">
                <circle cx="450" cy="730" r="5" fill="oklch(0.78 0.16 85 / 0.55)" className="node-pulse node-delay-5" />
                <circle cx="450" cy="730" r="2.5" fill="oklch(0.78 0.16 85 / 0.85)" />
                <text x="462" y="734" fill="oklch(0.78 0.16 85 / 0.4)" fontSize="10" fontFamily="system-ui, sans-serif" letterSpacing="1">快手</text>
              </g>

              {/* 贴吧 */}
              <g className="network-node">
                <circle cx="780" cy="600" r="5" fill="oklch(0.78 0.16 85 / 0.55)" className="node-pulse node-delay-6" />
                <circle cx="780" cy="600" r="2.5" fill="oklch(0.78 0.16 85 / 0.85)" />
                <text x="792" y="604" fill="oklch(0.78 0.16 85 / 0.4)" fontSize="10" fontFamily="system-ui, sans-serif" letterSpacing="1">贴吧</text>
              </g>

              {/* Central hub — aligned to Omnis text */}
              <circle cx={hubPos.x} cy={hubPos.y} r="7" fill="oklch(0.78 0.16 85 / 0.3)" className="node-pulse" />
              <circle cx={hubPos.x} cy={hubPos.y} r="3" fill="oklch(0.78 0.16 85 / 0.75)" />
            </g>

          </svg>
        </div>

        <div className="relative z-10 w-full max-w-4xl flex flex-col items-start gap-10 ml-10 pt-10">
          {/* Brand identity */}
          <div className="fade-in-up mt-24">
            <h1 ref={omnisRef} className="serif-headline text-7xl font-bold tracking-tight" style={{ color: 'var(--on-surface)' }}>
              Omnis
            </h1>
            <div className="mt-4 w-20 h-[2px]" style={{ background: 'var(--primary-gold)' }} />
          </div>

          {/* Hero text */}
          <div className="space-y-6 fade-in-up fade-in-up-1 mt-16">
            <h2 className="serif-headline text-5xl leading-tight" style={{ color: 'var(--on-surface)' }}>
              Where AI<br />
              <span className="italic font-semibold" style={{ color: 'var(--primary-gold)' }}>Meets Media Intelligence.</span>
            </h2>
            <p className="text-xl text-[var(--on-surface-variant)] max-w-xl leading-relaxed fade-in-up fade-in-up-2">
              主流媒体智能情报中枢，聚合全域信息流，集智能搜集、过滤审查、实时监测与深度分析于一体，洞察先机
            </p>
          </div>
        </div>
      </section>

      {/* Right 30% — Login form */}
      <main
        className="bg-white flex flex-col justify-start px-12 lg:px-16 pt-10 relative z-10 overflow-hidden"
        style={{ width: '30%' }}
      >
        {/* Mobile brand display */}
        <div className="lg:hidden absolute top-12 left-12">
          <span className="serif-headline text-3xl font-bold" style={{ color: 'var(--on-surface)' }}>Omnis</span>
        </div>

        <div className="w-full max-w-sm mx-auto animate-fade-up">
          <div className="mb-5">
            <h3 className="serif-headline text-3xl mb-3" style={{ color: 'var(--on-surface)' }}>
              {mode === 'login' ? '欢迎回来' : '创建账号'}
            </h3>
            <p className="text-[var(--on-surface-variant)]">
              {mode === 'login' ? '访问您的分析控制台。' : '加入智能情报网络。'}
            </p>
          </div>

          {/* Mode toggle (preserved from existing logic) */}
          <div className="flex items-center gap-2 mb-6 p-1 rounded-lg" style={{ background: 'oklch(0 0 0 / 0.03)' }}>
            <button
              type="button"
              onClick={() => setMode('login')}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${
                mode === 'login' ? 'bg-white shadow-sm' : 'text-[var(--on-surface-variant)] hover:text-[var(--on-surface)]'
              }`}
              style={mode === 'login' ? { color: 'var(--on-surface)' } : undefined}
            >
              登录
            </button>
            <button
              type="button"
              onClick={() => setMode('register')}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${
                mode === 'register' ? 'bg-white shadow-sm' : 'text-[var(--on-surface-variant)] hover:text-[var(--on-surface)]'
              }`}
              style={mode === 'register' ? { color: 'var(--on-surface)' } : undefined}
            >
              注册
            </button>
          </div>

          <form onSubmit={handleEmailAuth}>
            <div className="space-y-2 mb-6">
              <label className="label-caps text-[10px] text-[var(--on-surface-variant)] block" htmlFor="email">
                邮箱地址
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full px-5 py-4 rounded-lg border-[0.5px] text-sm transition-all outline-none"
                style={{
                  background: 'var(--bg-inner)',
                  borderColor: 'var(--border-faint)',
                  color: 'var(--on-surface)',
                }}
                onFocus={e => { e.target.style.borderColor = 'var(--primary-gold)'; e.target.style.boxShadow = '0 0 0 2px oklch(0.78 0.16 85 / 0.2)'; }}
                onBlur={e => { e.target.style.borderColor = 'var(--border-faint)'; e.target.style.boxShadow = 'none'; }}
                placeholder="analyst@mediaradar.ai"
                autoComplete="email"
              />
            </div>

            {mode === 'register' && (
            <div className="space-y-2 mb-6">
              <label className="label-caps text-[10px] text-[var(--on-surface-variant)] block" htmlFor="nickname">
                昵称
              </label>
              <input
                id="nickname"
                value={nickname}
                onChange={e => setNickname(e.target.value)}
                className="w-full px-5 py-4 rounded-lg border-[0.5px] text-sm transition-all outline-none"
                style={{
                  background: 'var(--bg-inner)',
                  borderColor: 'var(--border-faint)',
                  color: 'var(--on-surface)',
                }}
                onFocus={e => { e.target.style.borderColor = 'var(--primary-gold)'; e.target.style.boxShadow = '0 0 0 2px oklch(0.78 0.16 85 / 0.2)'; }}
                onBlur={e => { e.target.style.borderColor = 'var(--border-faint)'; e.target.style.boxShadow = 'none'; }}
                placeholder="您的显示名称"
              />
            </div>
            )}

            <div className="space-y-2 mb-6">
              <div className="flex justify-between items-center">
                <label className="label-caps text-[10px] text-[var(--on-surface-variant)]" htmlFor="password">
                  密码
                </label>
                {mode === 'login' && (
                  <a className="label-caps text-[10px] transition-colors" href="#" style={{ color: 'var(--primary-gold)' }}>
                    忘记密码?
                  </a>
                )}
              </div>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full px-5 py-4 rounded-lg border-[0.5px] text-sm transition-all outline-none"
                  style={{
                    background: 'var(--bg-inner)',
                    borderColor: 'var(--border-faint)',
                    color: 'var(--on-surface)',
                  }}
                  onFocus={e => { e.target.style.borderColor = 'var(--primary-gold)'; e.target.style.boxShadow = '0 0 0 2px oklch(0.78 0.16 85 / 0.2)'; }}
                  onBlur={e => { e.target.style.borderColor = 'var(--border-faint)'; e.target.style.boxShadow = 'none'; }}
                  placeholder={mode === 'register' ? '至少 6 个字符' : '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022'}
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 transition-colors"
                  style={{ color: 'var(--on-surface-variant)' }}
                >
                  <span className="material-symbols-outlined text-xl">{showPassword ? 'visibility_off' : 'visibility'}</span>
                </button>
              </div>
            </div>

            {mode === 'login' && (
            <div className="flex items-center gap-3 mb-6">
              <input
                id="remember"
                type="checkbox"
                className="w-4 h-4 rounded-sm transition-colors cursor-pointer"
                style={{ borderColor: 'var(--border-faint)', accentColor: 'var(--primary-gold)' }}
              />
              <label htmlFor="remember" className="text-sm cursor-pointer select-none" style={{ color: 'var(--on-surface-variant)' }}>
                保持 30 天登录状态
              </label>
            </div>
            )}

            <button
              type="submit"
              disabled={pending !== null}
              className="w-full brushed-gold hover:opacity-95 text-lg py-4 rounded-xl shadow-lg transition-all active:scale-[0.98] flex items-center justify-center gap-3 brushed-gold-text font-bold serif-headline mb-2"
              style={{ opacity: pending !== null ? 0.7 : 1 }}
            >
              <span>{pending === 'email' ? '处理中...' : (mode === 'login' ? '登录' : '注册')}</span>
              {pending !== 'email' && <span className="material-symbols-outlined text-xl">arrow_forward</span>}
            </button>
          </form>

          {/* Social connect */}
          <div className="mt-8">
            <div className="relative mb-5">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-[var(--border-faint)]" /></div>
              <div className="relative flex justify-center">
                <span className="bg-white px-4 text-[10px] label-caps text-[var(--on-surface-variant)]">或者通过以下方式登录</span>
              </div>
            </div>
            <button
              onClick={handleGoogleLogin}
              disabled={pending !== null}
              className="w-full flex items-center justify-center gap-3 py-3.5 border rounded-lg transition-all label-caps text-[10px] hover:bg-[oklch(0_0_0/0.04)] hover:border-[oklch(0_0_0/0.2)]"
              style={{
                borderColor: 'oklch(0 0 0 / 0.1)',
                background: 'oklch(0 0 0 / 0.03)',
                color: 'var(--on-surface)',
                opacity: pending !== null ? 0.5 : 1,
              }}
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
              <span>Google 账号登录</span>
            </button>
          </div>

          <p className="mt-4 text-center text-sm text-[var(--on-surface-variant)]">
            还没有账号？
            <button type="button" onClick={() => setMode('register')} className="font-bold hover:underline ml-1" style={{ color: 'var(--primary-gold)' }}>
              注册
            </button>
            或
            <button
              type="button"
              onClick={handleGuestLogin}
              disabled={pending !== null}
              className="font-bold hover:underline ml-1 inline"
              style={{ color: 'var(--primary-gold)', opacity: pending !== null ? 0.6 : 1 }}
            >
              {pending === 'guest' ? '处理中...' : '游客访问'}
            </button>
          </p>
        </div>

        {/* Footer */}
        <div className="absolute bottom-12 left-0 right-0 px-16 flex justify-between items-center opacity-30 pointer-events-none">
          <span className="label-caps text-[10px]">v2.4.0-A</span>
          <span className="label-caps text-[10px]">&copy; 2026 Omnis 系统</span>
        </div>
      </main>

      {/* Responsive: hide left panel on small screens */}
      <style>{`
        @media (max-width: 1024px) {
          .split-70 { display: none !important; }
          main { width: 100% !important; }
          body { overflow: auto; }
        }

        /* --- Animations --- */

        /* Fade-in-up for text elements */
        .fade-in-up {
          opacity: 0;
          transform: translateY(20px);
          animation: fadeInUp 0.8s cubic-bezier(0.22, 1, 0.36, 1) forwards;
        }
        .fade-in-up-1 { animation-delay: 0.15s; }
        .fade-in-up-2 { animation-delay: 0.35s; }

        @keyframes fadeInUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        /* Node pulse animation */
        .node-pulse {
          transform-origin: center;
          animation: nodePulse 3s ease-in-out infinite;
        }
        .node-delay-1 { animation-delay: 0.4s; }
        .node-delay-2 { animation-delay: 0.8s; }
        .node-delay-3 { animation-delay: 1.2s; }
        .node-delay-4 { animation-delay: 1.6s; }
        .node-delay-5 { animation-delay: 2.0s; }
        .node-delay-6 { animation-delay: 2.4s; }

        @keyframes nodePulse {
          0%, 100% {
            opacity: 0.35;
            r: 5;
          }
          50% {
            opacity: 0.9;
            r: 8;
          }
        }

        /* Edge flow animation — dash offset scroll */
        .edge-flow {
          stroke-dashoffset: 0;
          animation: edgeFlow 4s linear infinite;
        }

        @keyframes edgeFlow {
          to {
            stroke-dashoffset: -18;
          }
        }

        /* Drift float — entire network gently sways */
        .network-float {
          animation: netDrift 8s ease-in-out infinite;
        }

        @keyframes netDrift {
          0%, 100% {
            transform: translate(0, 0) rotate(0deg);
          }
          25% {
            transform: translate(8px, -6px) rotate(0.6deg);
          }
          50% {
            transform: translate(-4px, -10px) rotate(-0.4deg);
          }
          75% {
            transform: translate(6px, -3px) rotate(0.7deg);
          }
        }
      `}</style>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center text-sm text-[var(--on-surface-variant)]">加载中&hellip;</div>}>
      <LoginForm />
    </Suspense>
  );
}
