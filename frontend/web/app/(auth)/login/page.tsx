'use client';

import { useState, useEffect, Suspense } from 'react';
import Image from 'next/image';
import { useRouter, useSearchParams } from 'next/navigation';
import { authApi } from '@/lib/api';
import { persistAuth } from '@/lib/auth-client';
import { toast } from 'sonner';
import pkg from '@/package.json';

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
  const [ready, setReady] = useState(false);

  useEffect(() => {
    requestAnimationFrame(() => setReady(true));
  }, []);

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
    <div className={`light flex min-h-screen w-full relative overflow-hidden ${ready ? 'reveal-ready' : ''}`}>
      {/* Left 70% — Brand narrative (from login.html design) */}
      <section
        className="hidden lg:flex relative items-center justify-center pt-4 pl-12 pr-16 pb-16 overflow-hidden"
        style={{
          width: '70%',
          background: 'var(--background)',
          borderRight: '0.5px solid oklch(0 0 0 / 0.06)',
        }}
      >
        {/* Ambient background */}
        <div className="absolute inset-0 z-0">
          <div
            className="absolute -top-[10%] -left-[10%] w-[50%] h-[50%] rounded-full"
            style={{ background: 'oklch(0.78 0.16 85 / 0.10)', filter: 'blur(120px)' }}
          />
          <div
            className="absolute -bottom-[10%] -right-[10%] w-[40%] h-[40%] rounded-full"
            style={{ background: 'oklch(0.95 0.03 155 / 0.3)', filter: 'blur(100px)' }}
          />
        </div>




        {/* Message waterfall */}
        <div className="msg-waterfall">
          <div className="msg-item" style={{ left: '11.6%', animationDelay: '-1.8s', animationDuration: '32.3s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '12px' }}>华为 Mate 80 折叠屏跑分曝光，性能提升 40%</span>
          </div>
          <div className="msg-item" style={{ left: '23.5%', animationDelay: '-1.5s', animationDuration: '28.8s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '12px' }}>青岛三天两夜旅游攻略，人均 800 玩到爽</span>
          </div>
          <div className="msg-item" style={{ left: '37.7%', animationDelay: '-0.8s', animationDuration: '33.9s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '12px' }}>今天在银行排队一小时，VIP 插队太离谱了</span>
          </div>
          <div className="msg-item" style={{ left: '45.0%', animationDelay: '-0.2s', animationDuration: '24.3s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>朝阳区新开的日式烧肉店，和牛入口即化</span>
          </div>
          <div className="msg-item" style={{ left: '55.3%', animationDelay: '0.7s', animationDuration: '37.4s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '12px' }}>小米 SU7 实测续航达成率 92%，超出预期</span>
          </div>
          <div className="msg-item" style={{ left: '7.4%', animationDelay: '2.0s', animationDuration: '24.3s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>吐槽一下：某互联网大厂又开始变相裁员了</span>
          </div>
          <div className="msg-item" style={{ left: '22.3%', animationDelay: '3.4s', animationDuration: '36.3s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '12px' }}>故宫雪景美哭了，这才是北平的冬天</span>
          </div>
          <div className="msg-item" style={{ left: '31.2%', animationDelay: '4.1s', animationDuration: '32.6s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '12px' }}>邻居家的猫会开门，我家猫只会拆家</span>
          </div>
          <div className="msg-item" style={{ left: '50.3%', animationDelay: '5.4s', animationDuration: '28.2s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>三亚海鲜市场避雷指南，本地人教你挑</span>
          </div>
          <div className="msg-item" style={{ left: '55.9%', animationDelay: '6.2s', animationDuration: '31.6s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>苹果 Vision Pro 销量惨淡，库克急了</span>
          </div>
          <div className="msg-item" style={{ left: '7.0%', animationDelay: '6.6s', animationDuration: '34.1s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>周末去了一趟莫干山，民宿绝了</span>
          </div>
          <div className="msg-item" style={{ left: '27.4%', animationDelay: '7.8s', animationDuration: '36.6s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>某品牌奶茶被曝使用过期原料，网友炸了</span>
          </div>
          <div className="msg-item" style={{ left: '32.9%', animationDelay: '8.1s', animationDuration: '33.8s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '12px' }}>DeepSeek V4 发布，编程能力碾压 GPT</span>
          </div>
          <div className="msg-item" style={{ left: '48.5%', animationDelay: '9.7s', animationDuration: '26.9s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '12px' }}>成都苍蝇馆子地图，不好吃你来打我</span>
          </div>
          <div className="msg-item" style={{ left: '57.9%', animationDelay: '10.7s', animationDuration: '34.8s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '12px' }}>特斯拉 FSD 入华，国产智驾还扛得住吗</span>
          </div>
          <div className="msg-item" style={{ left: '16.4%', animationDelay: '11.7s', animationDuration: '28.5s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>今天坐高铁遇到个话痨师傅，一路没停</span>
          </div>
          <div className="msg-item" style={{ left: '28.6%', animationDelay: '12.0s', animationDuration: '30.1s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>大理洱海骑行攻略，风景比照片美十倍</span>
          </div>
          <div className="msg-item" style={{ left: '38.2%', animationDelay: '13.2s', animationDuration: '30.8s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '12px' }}>老板画饼新高度：我们要做 AI 界的 Swisse</span>
          </div>
          <div className="msg-item" style={{ left: '50.4%', animationDelay: '13.6s', animationDuration: '25.5s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>Switch 2 确认向下兼容，老玩家落泪</span>
          </div>
          <div className="msg-item" style={{ left: '61.1%', animationDelay: '14.3s', animationDuration: '28.2s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>长沙夜市从头吃到尾，只花了 100 块</span>
          </div>
          <div className="msg-item" style={{ left: '9.3%', animationDelay: '16.2s', animationDuration: '32.9s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>OpenAI 新模型被指套壳，AI 圈又吵起来了</span>
          </div>
          <div className="msg-item" style={{ left: '23.5%', animationDelay: '16.9s', animationDuration: '35.5s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>北海涠洲岛避坑：别被黄牛宰了</span>
          </div>
          <div className="msg-item" style={{ left: '31.1%', animationDelay: '18.0s', animationDuration: '35.7s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '12px' }}>发现一家宝藏咖啡馆，老板是前阿里 P8</span>
          </div>
          <div className="msg-item" style={{ left: '48.3%', animationDelay: '18.5s', animationDuration: '29.5s' }}>
            <span className="msg-dot"></span>
            <span className="msg-text" style={{ fontSize: '11px' }}>B站 UP 主停更潮背后：用爱发电撑不住了</span>
          </div>
        </div>
                {/* Content Container */}
        <div className="relative z-10 w-full max-w-4xl flex flex-col items-start gap-8">
          {/* Brand logo + divider */}
          <div className="flex flex-col gap-2 phase-logo">
            <div className="logo-shimmer logo-reveal-wrap">
              <Image
                src="/logo.svg"
              alt="Omnis"
              width={500}
              height={80}
              priority
              unoptimized
              style={{ marginLeft: '-10px' }}
            />
              </div>
          </div>

            {/* 5 core capability keywords */}
            <div className="flex flex-wrap gap-x-5 gap-y-1.5 mt-1 mb-8 phase-keywords">
              <span className="keyword-item flex items-center gap-1.5">
                <span className="w-[5px] h-[5px] rounded-full" style={{ background: 'var(--primary-gold)' }}></span>
                <span className="font-medium text-sm font-cn" style={{ color: 'var(--on-surface)' }}>舆情监控</span>
              </span>
              <span className="keyword-item flex items-center gap-1.5">
                <span className="w-[5px] h-[5px] rounded-full" style={{ background: 'var(--primary-gold)' }}></span>
                <span className="font-medium text-sm font-cn" style={{ color: 'var(--on-surface)' }}>攻略规划</span>
              </span>
              <span className="keyword-item flex items-center gap-1.5">
                <span className="w-[5px] h-[5px] rounded-full" style={{ background: 'var(--primary-gold)' }}></span>
                <span className="font-medium text-sm" style={{ color: 'var(--on-surface)' }}>实体追踪</span>
              </span>
              <span className="keyword-item flex items-center gap-1.5">
                <span className="w-[5px] h-[5px] rounded-full" style={{ background: 'var(--primary-gold)' }}></span>
                <span className="font-medium text-sm" style={{ color: 'var(--on-surface)' }}>跨平台对比</span>
              </span>
              <span className="keyword-item flex items-center gap-1.5">
                <span className="w-[5px] h-[5px] rounded-full" style={{ background: 'var(--primary-gold)' }}></span>
                <span className="font-medium text-sm" style={{ color: 'var(--on-surface)' }}>工作流自动化</span>
              </span>
            </div>

          {/* Tagline + description + globe network */}
          <div className="relative space-y-2 mb-2 w-full phase-text">
            <h2
              className="serif-headline text-2xl leading-tight"
              style={{ color: 'var(--on-surface)' }}
            >
              where Agents meet{' '}
              <span className="italic font-semibold" style={{ color: 'var(--primary-gold)' }}>
                Media Intelligence
              </span>
            </h2>
            <p
              className="text-sm italic font-cn"
              style={{
                color: 'oklch(0.35 0.01 280 / 0.55)',
                borderBottom: '1px solid oklch(0.78 0.16 85 / 0.5)',
                paddingBottom: '6px',
                display: 'inline-block',
              }}
            >
              跨平台媒体信息数据采集与分析智能体
            </p>
          </div>
        </div>
      </section>

      {/* Right 30% — Login form (mostly unchanged) */}
      <main
        className="bg-white flex flex-col justify-start px-12 lg:px-16 pt-20 relative z-10 overflow-hidden"
        style={{ width: '30%' }}
      >
        {/* Mobile brand display */}
        <div className="lg:hidden absolute top-12 left-12">
          <span className="serif-headline text-3xl font-bold" style={{ color: 'var(--on-surface)' }}>Omnis</span>
        </div>

        <div className="w-full max-w-sm mx-auto animate-fade-up phase-right">
          <div className="mb-5">
            <h3 className="serif-headline text-3xl mb-3" style={{ color: 'var(--on-surface)' }}>
              {mode === 'login' ? '欢迎回来' : '创建账号'}
            </h3>
            <p style={{ color: 'var(--on-surface-variant)' }}>
              {mode === 'login' ? '访问您的分析控制台' : '加入智能情报网络'}
            </p>
          </div>

          {/* Mode toggle */}
          <div className="flex items-center gap-2 mb-6 p-1 rounded-lg" style={{ background: 'oklch(0 0 0 / 0.03)' }}>
            <button
              type="button"
              onClick={() => setMode('login')}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${
                mode === 'login' ? 'bg-white shadow-sm' : 'hover:text-[var(--on-surface)]'
              }`}
              style={mode === 'login' ? { color: 'var(--on-surface)' } : { color: 'var(--on-surface-variant)' }}
            >
              登录
            </button>
            <button
              type="button"
              onClick={() => setMode('register')}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${
                mode === 'register' ? 'bg-white shadow-sm' : 'hover:text-[var(--on-surface)]'
              }`}
              style={mode === 'register' ? { color: 'var(--on-surface)' } : { color: 'var(--on-surface-variant)' }}
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

            {/* Brushed-gold submit button — matching login.html style */}
            <button
              type="submit"
              disabled={pending !== null}
              className="brushed-gold hover:opacity-95 w-full text-lg py-2 rounded-xl shadow-lg transition-all active:scale-[0.98] flex items-center justify-center gap-3 brushed-gold-text font-bold serif-headline mb-2"
              style={{ opacity: pending !== null ? 0.7 : 1 }}
            >
              <span>{pending === 'email' ? '处理中...' : (mode === 'login' ? '登录' : '注册')}</span>
              {pending !== 'email' && <span className="material-symbols-outlined text-xl">arrow_forward</span>}
            </button>
          </form>

          {/* Social connect */}
          <div className="mt-8">
            <div className="relative mb-5">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t" style={{ borderColor: 'var(--border-faint)' }} /></div>
              <div className="relative flex justify-center">
                <span className="bg-white px-4 text-[10px] label-caps" style={{ color: 'var(--on-surface-variant)' }}>
                  或者通过以下方式登录
                </span>
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

          <p className="mt-4 text-center text-sm" style={{ color: 'var(--on-surface-variant)' }}>
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
          <span className="label-caps text-[10px]">{`v${pkg.version}`}</span>
          <span className="label-caps text-[10px]">&copy; 2026 Omnis 系统</span>
        </div>
      </main>

      {/* Styles */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=LXGW+WenKai:wght@400;700&display=swap');
        /* Force light mode for the entire page */
        .light {
          --background: oklch(0.97 0.005 280);
          --on-surface: #1a1a18;
          --on-surface-variant: #4a4a48;
          --primary-gold: oklch(0.78 0.16 85);
        }
        .light,
        .light * {
          color-scheme: light;
        }

        /* ── Feature cards: staggered float ── */





        @keyframes cardFloat {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-10px); }
        }









        /* ── Entrance system ── */

        /* Hidden elements (activated by .reveal-ready) */
        .phase-right,
        .phase-logo,
        .phase-text {
          opacity: 0;
        }

        /* Right side: appears first */
        .reveal-ready .phase-right {
          animation: fadeSlideRight 0.5s cubic-bezier(0.16, 1, 0.3, 1) 0.1s both;
        }
        @keyframes fadeSlideRight {
          0% { opacity: 0; transform: translateY(12px); }
          100% { opacity: 1; transform: translateY(0); }
        }

        /* OMNIS logo: starts immediately, slow 2.5s left-to-right reveal */
        .reveal-ready .phase-logo {
          opacity: 1;
        }
        .logo-reveal-wrap {
          display: inline-block;
          clip-path: inset(0 100% 0 0);
        }
        .reveal-ready .logo-reveal-wrap {
          animation: logoReveal 2.5s cubic-bezier(0.25, 0.1, 0.25, 1) 0s both;
        }
        @keyframes logoReveal {
          0% { clip-path: inset(0 100% 0 0); filter: brightness(0.6); }
          40% { filter: brightness(1.1); }
          100% { clip-path: inset(0 0% 0 0); filter: brightness(1); }
        }

        /* 5 keywords: stagger during logo reveal */
        .phase-keywords { opacity: 0; }
        .reveal-ready .phase-keywords { opacity: 1; }
        .reveal-ready .keyword-item {
          opacity: 0;
          animation: keywordPop 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        .reveal-ready .keyword-item:nth-child(1) { animation-delay: 0.3s; }
        .reveal-ready .keyword-item:nth-child(2) { animation-delay: 0.6s; }
        .reveal-ready .keyword-item:nth-child(3) { animation-delay: 0.9s; }
        .reveal-ready .keyword-item:nth-child(4) { animation-delay: 1.2s; }
        .reveal-ready .keyword-item:nth-child(5) { animation-delay: 1.5s; }
        @keyframes keywordPop {
          0% { opacity: 0; transform: translateY(6px) scale(0.95); }
          100% { opacity: 1; transform: translateY(0) scale(1); }
        }

        /* Tagline + description: after logo reveal */
        .reveal-ready .phase-text {
          animation: fadeSlideUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) 2.5s both;
        }
        @keyframes fadeSlideUp {
          0% { opacity: 0; transform: translateY(24px); }
          100% { opacity: 1; transform: translateY(0); }
        }

        /* --- Logo subtle gold shimmer (loops after reveal) --- */
        .logo-shimmer {
          animation: goldShimmer 4s ease-in-out 2.2s infinite;
        }
        @keyframes goldShimmer {
          0%, 100% { filter: brightness(1) saturate(1); }
          50% { filter: brightness(1.06) saturate(1.05); }
        }

        /* --- Message waterfall --- */
        .msg-waterfall {
          position: absolute;
          top: 0;
          right: 0;
          width: 44%;
          height: 100%;
          pointer-events: none;
          overflow: hidden;
          z-index: 1;
        }
        .msg-item {
          position: absolute;
          display: inline-flex;
          align-items: flex-start;
          gap: 5px;
          padding: 7px 11px;
          border-radius: 10px;
          background: rgba(255, 255, 255, 0.35);
          backdrop-filter: blur(8px);
          border: 0.5px solid oklch(0.78 0.16 85 / 0.08);
          box-shadow: 0 2px 8px rgba(0,0,0,0.02);
          white-space: nowrap;
          animation: msgRise ease-in-out infinite;
          animation-fill-mode: both;
        }
        .msg-dot {
          width: 5px;
          height: 5px;
          min-width: 5px;
          border-radius: 50%;
          margin-top: 4px;
          background: oklch(0.78 0.16 85 / 0.3);
        }
        .msg-text {
          color: oklch(0.15 0.01 280 / 0.45);
          line-height: 1.4;
          letter-spacing: 0.2px;
          overflow: hidden;
          text-overflow: ellipsis;
          max-width: 160px;
        }
        @keyframes msgRise {
          0% { top: 105%; opacity: 0; }
          2% { opacity: 0.5; }
          6% { opacity: 0.8; }
          72% { opacity: 0.55; }
          90% { opacity: 0; transform: translateX(6px); }
          100% { top: -15%; opacity: 0; transform: translateX(6px); }
        }

@media (max-width: 1024px) {
          .split-70 { display: none !important; }
          main { width: 100% !important; }
          body { overflow: auto; }
        }
      `}</style>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center text-sm" style={{ color: 'var(--on-surface-variant)' }}>加载中&hellip;</div>}>
      <LoginForm />
    </Suspense>
  );
}
