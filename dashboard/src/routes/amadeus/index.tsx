import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity, Bot, Brain, Cpu, HardDrive, MessageCircle, Mic,
  Monitor, Power, RotateCw, Volume2, ExternalLink,
} from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { cn } from '@/lib/utils'
import { isElectron } from '@/lib/runtime'

// ── 类型 ──────────────────────────────────────────────────────────────────

interface AmadeusStatus {
  bot_running: boolean
  bot_start_time: string
  model_name: string
  model_context_window: number
  tts_enabled: boolean; tts_running: boolean
  memory_total_entries: number
  private_console_running: boolean
  uptime_seconds: number
  today_message_count: number
  cpu_percent: number; memory_percent: number
  memory_used_mb: number; memory_total_mb: number
  version: string; bot_nickname: string
}

// ── 格式化 ────────────────────────────────────────────────────────────────

function fmtUptime(s: number): string {
  if (s < 60) return `${Math.floor(s)}s`
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function fmtMem(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.floor(mb)} MB`
}

// ── 主组件 ────────────────────────────────────────────────────────────────

export function AmadeusHome() {
  const [status, setStatus] = useState<AmadeusStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [errorMsg, setErrorMsg] = useState('')
  const [actionBusy, setActionBusy] = useState<string | null>(null)
  const [actionMsg, setActionMsg] = useState('')
  const navigate = useNavigate()

  const apiFetch = useCallback(async (path: string, init?: RequestInit) => {
    const r = await fetch(`/api/webui${path}`, { credentials: 'include', ...init })
    if (!r.ok) {
      const t = await r.text()
      throw new Error(`${r.status}: ${t || r.statusText}`)
    }
    return r.json()
  }, [])

  const fetchStatus = useCallback(async () => {
    try {
      setStatus(await apiFetch('/amadeus/status'))
      setErrorMsg('')
    } catch (err) {
      console.error('[Amadeus]', err)
      setErrorMsg(err instanceof Error ? err.message : '未知错误')
    } finally { setLoading(false) }
  }, [apiFetch])

  useEffect(() => {
    fetchStatus()
    const id = setInterval(fetchStatus, 5000)
    return () => clearInterval(id)
  }, [fetchStatus])

  const doAction = useCallback(async (label: string, fn: () => Promise<any>) => {
    setActionBusy(label)
    setActionMsg('')
    try {
      const result = await fn()
      if (result?.message) setActionMsg(result.message)
      await fetchStatus()
      return result
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : '操作失败')
    } finally { setActionBusy(null) }
  }, [fetchStatus])

  // ── 启动私密控制台 ──────────────────────────────────────
  const handlePrivateConsole = useCallback(async () => {
    if (status?.private_console_running) {
      const tokenUrl = await apiFetch('/amadeus/private-console/status').then(
        (s: any) => s.url || 'http://127.0.0.1:7860'
      ).catch(() => 'http://127.0.0.1:7860')
      if (isElectron() && window.electronAPI) await window.electronAPI.openExternalUrl(tokenUrl)
      else window.open(tokenUrl, '_blank')
      return
    }
    const result = await doAction('console', () => apiFetch('/amadeus/private-console/launch', { method: 'POST' }))
    if (result?.url) {
      // 等一秒让服务起来，然后打开
      await new Promise(r => setTimeout(r, 1500))
      if (isElectron() && window.electronAPI) await window.electronAPI.openExternalUrl(result.url)
      else window.open(result.url, '_blank')
    }
  }, [status, doAction, apiFetch])

  const handleStopPrivateConsole = useCallback(async () => {
    await doAction('stop-console', () => apiFetch('/amadeus/private-console/stop', { method: 'POST' }))
  }, [doAction, apiFetch])

  // ── 启动 TTS ────────────────────────────────────────────
  const handleTTS = useCallback(async () => {
    if (status?.tts_running) return
    await doAction('tts', () => apiFetch('/amadeus/tts/launch', { method: 'POST' }))
  }, [status, doAction, apiFetch])

  const handleStopTTS = useCallback(async () => {
    await doAction('stop-tts', () => apiFetch('/amadeus/tts/stop', { method: 'POST' }))
  }, [doAction, apiFetch])

  // ── 停止 Bot ────────────────────────────────────────────
  const handleStopBot = useCallback(async () => {
    await doAction('stop', () => apiFetch('/amadeus/bot/stop', { method: 'POST' }))
  }, [doAction, apiFetch])

  // ── 渲染 ────────────────────────────────────────────────

  if (loading) return (
    <div className="flex h-full items-center justify-center bg-[#0a080c]">
      <RotateCw className="h-5 w-5 text-white/15 animate-spin" />
    </div>
  )

  if (!status) return (
    <div className="flex h-full items-center justify-center bg-[#0a080c]">
      <div className="text-center space-y-4 max-w-sm">
        <div className="text-white/35 text-sm">无法连接 Amadeus 后端</div>
        {errorMsg && <div className="text-red-400/60 text-xs font-mono break-all leading-relaxed">{errorMsg}</div>}
        <button onClick={fetchStatus}
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-4 py-2 text-white/60 text-sm
            hover:bg-white/5 hover:text-white/80 transition-colors">
          <RotateCw className="h-4 w-4" /> 重试
        </button>
      </div>
    </div>
  )

  return (
    <div className="h-full overflow-y-auto bg-[#0a080c] text-white">
      {/* 环境光 */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-48 right-1/4 w-[500px] h-[500px] rounded-full bg-rose-500/[0.04] blur-[120px]" />
        <div className="absolute -bottom-32 left-1/3 w-[400px] h-[400px] rounded-full bg-violet-500/[0.03] blur-[100px]" />
      </div>

      <div className="relative z-10 mx-auto max-w-4xl px-6 py-10 space-y-10">
        {/* ═══ 英雄区 ═══ */}
        <div className="flex items-start gap-10">
          {/* 立绘 */}
          <div className="shrink-0">
            <div className="w-48 h-64 rounded-2xl overflow-hidden border border-white/[0.07] bg-white/[0.03]
              shadow-[0_32px_80px_rgba(0,0,0,0.4)] group">
              <img src="/amadeus-portrait.png" alt="千惠"
                className="w-full h-full object-cover object-top transition-transform duration-700 group-hover:scale-105"
                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
            </div>
          </div>

          {/* 标题 + 操作 */}
          <div className="flex-1 space-y-6 pt-1">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-bold tracking-tight">
                  {status.bot_nickname || '千惠'}
                </h1>
                <span className="text-white/25 font-light text-xl">Amadeus</span>
              </div>
              <div className="flex items-center gap-3 text-white/30 text-sm">
                <span className="inline-flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${status.bot_running ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.4)]' : 'bg-red-400'}`} />
                  {status.bot_running ? '运行中' : '已停止'}
                </span>
                <span>·</span>
                <span>v{status.version}</span>
                <span>·</span>
                <span>{fmtUptime(status.uptime_seconds)}</span>
              </div>
            </div>

            {/* 操作按钮 */}
            <div className="flex flex-wrap items-center gap-2.5">
              <ActionBtn icon={Monitor}
                label={status.private_console_running ? '打开控制台' : '启动私密控制台'}
                active={status.private_console_running}
                busy={actionBusy === 'console'}
                variant={status.private_console_running ? 'active' : 'default'}
                onClick={handlePrivateConsole}
              />
              {status.private_console_running && (
                <ActionBtn icon={Power}
                  label="关闭控制台" busy={actionBusy === 'stop-console'} variant="danger"
                  onClick={handleStopPrivateConsole}
                />
              )}
              <ActionBtn icon={Volume2}
                label={status.tts_running ? '语音在线' : '启动语音'}
                active={status.tts_running}
                busy={actionBusy === 'tts'}
                variant={status.tts_running ? 'active' : 'default'}
                disabled={status.tts_running}
                onClick={handleTTS}
              />
              {status.tts_running && (
                <ActionBtn icon={Power}
                  label="关闭语音" busy={actionBusy === 'stop-tts'} variant="danger"
                  onClick={handleStopTTS}
                />
              )}
              <ActionBtn icon={Power} label="停止 Bot"
                busy={actionBusy === 'stop'} variant="danger"
                onClick={handleStopBot}
              />
            </div>
            {actionMsg && (
              <div className="text-xs text-white/40">{actionMsg}</div>
            )}
          </div>
        </div>

        {/* ═══ 状态卡片 ═══ */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
          <StatCard icon={Activity} label="Bot 状态"
            value={status.bot_running ? '运行中' : '已停止'}
            accent={status.bot_running ? 'emerald' : 'slate'} />
          <StatCard icon={Brain} label="模型"
            value={status.model_name.includes('/') ? status.model_name.split('/').pop()! : status.model_name}
            accent="purple" />
          <StatCard icon={HardDrive} label="上下文窗口"
            value={status.model_context_window ? `${status.model_context_window}` : '-'}
            accent="blue" />
          <StatCard icon={Bot} label="长期记忆"
            value={`${status.memory_total_entries} 条`}
            accent="amber" />
          <StatCard icon={Mic} label="语音服务"
            value={status.tts_running ? '在线' : '离线'}
            accent={status.tts_running ? 'emerald' : 'slate'} />
          <StatCard icon={Monitor} label="私密控制台"
            value={status.private_console_running ? '已启动' : '未启动'}
            accent={status.private_console_running ? 'emerald' : 'slate'} />
          <StatCard icon={MessageCircle} label="今日消息"
            value={`${status.today_message_count} 条`}
            accent="cyan" />
          <StatCard icon={Cpu} label="系统"
            value={status.memory_used_mb > 0
              ? `${status.cpu_percent.toFixed(0)}% · ${fmtMem(status.memory_used_mb)}`
              : `${status.cpu_percent.toFixed(0)}% CPU`}
            accent="slate" />
        </div>

        {/* ═══ 对话入口 ═══ */}
        <button
          onClick={() => navigate({ to: '/amadeus/chat' })}
          className="w-full rounded-2xl border border-white/[0.07] bg-white/[0.03] hover:bg-white/[0.06]
            hover:border-rose-500/15 p-6 text-left transition-all duration-300 group cursor-pointer"
        >
          <div className="flex items-center justify-between">
            <div className="space-y-1.5">
              <h3 className="font-semibold text-white/80 flex items-center gap-2 group-hover:text-white transition-colors">
                <MessageCircle className="h-4 w-4 text-rose-400/70" />
                与千惠对话
              </h3>
              <p className="text-white/30 text-sm">
                通过主 Bot 后端连接 · 与 QQ 群聊共享记忆和人格
              </p>
            </div>
            <div className="text-white/15 group-hover:text-white/40 group-hover:translate-x-1 transition-all duration-300">
              <ExternalLink className="h-5 w-5" />
            </div>
          </div>
        </button>
      </div>
    </div>
  )
}

// ── 状态卡片 ──────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, accent }: {
  icon: React.ComponentType<{ className?: string }>; label: string; value: string; accent: string
}) {
  const accents: Record<string, { border: string; bg: string; icon: string; glow: string }> = {
    emerald: { border: 'border-emerald-500/15', bg: 'bg-emerald-500/[0.04]', icon: 'text-emerald-400/60', glow: 'shadow-[inset_0_0_0_1px_rgba(52,211,153,0.06)]' },
    purple: { border: 'border-purple-500/15', bg: 'bg-purple-500/[0.04]', icon: 'text-purple-400/60', glow: 'shadow-[inset_0_0_0_1px_rgba(168,85,247,0.06)]' },
    blue:   { border: 'border-blue-500/15', bg: 'bg-blue-500/[0.04]', icon: 'text-blue-400/60', glow: 'shadow-[inset_0_0_0_1px_rgba(96,165,250,0.06)]' },
    amber:  { border: 'border-amber-500/15', bg: 'bg-amber-500/[0.04]', icon: 'text-amber-400/60', glow: 'shadow-[inset_0_0_0_1px_rgba(251,191,36,0.06)]' },
    cyan:   { border: 'border-cyan-500/15', bg: 'bg-cyan-500/[0.04]', icon: 'text-cyan-400/60', glow: 'shadow-[inset_0_0_0_1px_rgba(34,211,238,0.06)]' },
    slate:  { border: 'border-white/[0.06]', bg: 'bg-white/[0.02]', icon: 'text-white/25', glow: '' },
  }
  const a = accents[accent] || accents.slate
  return (
    <div className={cn(
      'rounded-xl border p-4 space-y-2.5 transition-colors duration-200',
      a.border, a.bg, a.glow,
    )}>
      <div className="flex items-center gap-2">
        <Icon className={cn('h-4 w-4', a.icon)} />
        <span className="text-[11px] font-medium uppercase tracking-widest text-white/25">{label}</span>
      </div>
      <div className="text-base font-semibold text-white/80">{value}</div>
    </div>
  )
}

// ── 操作按钮 ──────────────────────────────────────────────────────────────

function ActionBtn({ icon: Icon, label, active, busy, variant, disabled, onClick }: {
  icon: React.ComponentType<{ className?: string }>; label: string; active?: boolean
  busy?: boolean; variant: 'default' | 'active' | 'danger'; disabled?: boolean; onClick: () => void
}) {
  const base = 'inline-flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-all duration-150 hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-40 disabled:cursor-not-allowed disabled:translate-y-0'
  const variants = {
    default: 'border-white/[0.08] bg-white/[0.04] text-white/60 hover:bg-white/[0.08] hover:text-white/80 hover:border-white/15',
    active: 'border-emerald-500/20 bg-emerald-500/[0.08] text-emerald-300/80 hover:bg-emerald-500/[0.12]',
    danger: 'border-red-500/15 bg-red-500/[0.06] text-red-300/70 hover:bg-red-500/[0.1] hover:text-red-200',
  }
  return (
    <button onClick={onClick} disabled={busy || disabled} className={cn(base, variants[variant])}>
      {busy ? <RotateCw className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}
      {label}
      {active && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]" />}
    </button>
  )
}
