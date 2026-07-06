import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  Check,
  ChevronRight,
  CircleEllipsis,
  Eye,
  MessageCircle,
  RefreshCw,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  Volume2,
  WifiOff,
  X,
  type LucideIcon,
} from 'lucide-react'

import { TitleBar } from '@/components/electron/TitleBar'
import {
  amadeusApi,
  type AmadeusCommand,
  type AmadeusEvent,
  type AmadeusStatus,
  type RemoteConfig,
} from '@/lib/amadeus-api'
import { isElectron } from '@/lib/runtime'

import './amadeus.css'
import { useAmadeusChat } from './use-amadeus-chat'

const ACTION_LABELS: Record<string, string> = {
  'application.open': '打开程序',
  'command.run': '运行命令',
  'file.modify': '修改文件',
  'hardware.control': '控制硬件',
  'message.send': '发送消息',
  'voice.play': '播放语音',
}

function formatTime(value: string | number): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--:--'
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(date)
}

function formatUptime(seconds?: number): string {
  if (!seconds) return '刚刚连接'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days} 天 ${hours} 小时`
  if (hours > 0) return `${hours} 小时 ${minutes} 分`
  return `${Math.max(1, minutes)} 分钟`
}

function eventTitle(event: AmadeusEvent): string {
  const labels: Record<string, string> = {
    'service.online': '云端恢复连接',
    'service.offline': '云端失去连接',
    'service.start_requested': '正在启动语音',
    'service.stopped': '语音服务已停止',
    'chat.user_message': '你发送了消息',
    'chat.assistant_message': '千惠回复了消息',
    'command.created': '收到动作请求',
    'command.approved': '动作已批准',
    'command.rejected': '动作已拒绝',
    'remote.updated': '连接设置已更新',
  }
  return labels[event.event_type] || event.event_type.replaceAll('.', ' · ')
}

export function AmadeusHome() {
  const [status, setStatus] = useState<AmadeusStatus | null>(null)
  const [events, setEvents] = useState<AmadeusEvent[]>([])
  const [commands, setCommands] = useState<AmadeusCommand[]>([])
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [serviceBusy, setServiceBusy] = useState(false)
  const [decisionBusy, setDecisionBusy] = useState<string | null>(null)
  const [messageInput, setMessageInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const chatEnabled = Boolean(status?.remote.online && status?.identity.mapped)
  const chat = useAmadeusChat(chatEnabled)
  const pendingCommands = useMemo(
    () => commands.filter((command) => command.status === 'pending_approval'),
    [commands],
  )

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    const [statusResult, eventsResult, commandsResult] = await Promise.allSettled([
      amadeusApi.status(),
      amadeusApi.events(),
      amadeusApi.commands(),
    ])

    if (statusResult.status === 'fulfilled') {
      setStatus(statusResult.value)
      setBackendOnline(true)
      setNotice('')
    } else {
      setBackendOnline(false)
      setStatus(null)
      setNotice(statusResult.reason instanceof Error ? statusResult.reason.message : '本机 Amadeus 没有响应')
    }
    if (eventsResult.status === 'fulfilled') setEvents(eventsResult.value.events)
    if (commandsResult.status === 'fulfilled') setCommands(commandsResult.value.commands)
    setLoading(false)
  }, [])

  useEffect(() => {
    void refresh()
    const interval = window.setInterval(() => void refresh(true), 5000)
    return () => window.clearInterval(interval)
  }, [refresh])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chat.messages, chat.awaitingReply])

  const handleSend = useCallback(() => {
    if (chat.sendMessage(messageInput)) setMessageInput('')
  }, [chat, messageInput])

  const handleTts = useCallback(async () => {
    setServiceBusy(true)
    try {
      if (status?.local.tts.running || status?.local.tts.state === 'starting') {
        await amadeusApi.ttsStop()
      } else {
        await amadeusApi.ttsStart()
      }
      await refresh(true)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '语音服务操作失败')
    } finally {
      setServiceBusy(false)
    }
  }, [refresh, status])

  const handleDecision = useCallback(async (commandId: string, approved: boolean) => {
    setDecisionBusy(commandId)
    try {
      await amadeusApi.decideCommand(commandId, approved)
      await refresh(true)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '审批操作失败')
    } finally {
      setDecisionBusy(null)
    }
  }, [refresh])

  const handleDeleteEvent = useCallback(async (eventId: string) => {
    try {
      await amadeusApi.deleteEvent(eventId)
      setEvents((current) => current.filter((event) => event.id !== eventId))
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '删除记录失败')
    }
  }, [])

  const localReady = backendOnline === true
  const remoteReady = Boolean(status?.remote.online)
  const identityReady = Boolean(status?.identity.mapped)
  const voiceReady = Boolean(status?.local.tts.running)

  return (
    <div className="amadeus-window">
      {isElectron() && <TitleBar title="AMADEUS · 千惠" variant="amadeus" />}
      <main className="amadeus-shell">
        <header className="amadeus-topbar">
          <div className="amadeus-wordmark">
            <span className="amadeus-wordmark-mark"><b>A</b></span>
            <div>
              <strong>AMADEUS</strong>
              <span>CHIE LOCAL CONTROL</span>
            </div>
          </div>
          <div className="amadeus-topbar-actions">
            {pendingCommands.length > 0 && (
              <span className="amadeus-attention-pill">
                <CircleEllipsis aria-hidden="true" />
                {pendingCommands.length} 项待确认
              </span>
            )}
            <button className="amadeus-icon-button" onClick={() => void refresh()} aria-label="刷新状态">
              <RefreshCw className={loading ? 'is-spinning' : ''} />
            </button>
            <button className="amadeus-icon-button" onClick={() => setSettingsOpen(true)} aria-label="连接设置">
              <Settings2 />
            </button>
          </div>
        </header>

        {notice && (
          <div className="amadeus-notice" role="status">
            <AlertTriangle aria-hidden="true" />
            <span>{notice}</span>
            <button onClick={() => setNotice('')} aria-label="关闭提示"><X /></button>
          </div>
        )}

        {backendOnline === false ? (
          <BackendOffline onRetry={() => void refresh()} />
        ) : (
          <div className="amadeus-workspace">
            <aside className="amadeus-identity-panel">
              <section className="amadeus-portrait-stage" aria-label="千惠状态">
                <div className="amadeus-portrait-halo" />
                <img src="/amadeus-portrait.png" alt="千惠" />
                <div className="amadeus-portrait-caption">
                  <span className={`amadeus-presence-dot ${remoteReady ? 'is-online' : ''}`} />
                  <div>
                    <strong>{status?.remote.bot_nickname || '千惠'}</strong>
                    <span>{remoteReady ? '现在在线' : '云端没有回应'}</span>
                  </div>
                </div>
              </section>

              <p className="amadeus-presence-copy">
                {remoteReady
                  ? identityReady
                    ? `我在。已认出你是${status?.identity.display_name || '主人'}。`
                    : '我在线，但还没有认出这台设备上的你。'
                  : '云端暂时没有回应。Amadeus 仍在本机守着。'}
              </p>

              <section className="amadeus-life-line" aria-label="连接生命线">
                <LifeNode label="云端千惠" detail={remoteReady ? `已运行 ${formatUptime(status?.remote.uptime_seconds)}` : '等待回应'} active={remoteReady} />
                <div className={`amadeus-neural-link ${remoteReady && localReady ? 'is-linked' : ''}`}>
                  <i /><i /><i />
                </div>
                <LifeNode label="本机 Amadeus" detail="127.0.0.1 · 私有" active={localReady} />
              </section>

              <section className="amadeus-capabilities" aria-label="本机能力">
                <CapabilityButton
                  icon={Volume2}
                  label="语音"
                  detail={voiceReady ? '千惠可以发声' : status?.local.tts.state === 'starting' ? '正在唤醒声音' : '当前静音'}
                  active={voiceReady}
                  busy={serviceBusy}
                  onClick={() => void handleTts()}
                />
                <CapabilityButton icon={Eye} label="视觉" detail="后续接入" disabled />
              </section>
            </aside>

            <section className="amadeus-chat-panel">
              <div className="amadeus-panel-heading">
                <div>
                  <span className="amadeus-eyebrow">PRIVATE CHANNEL</span>
                  <h1>和千惠说话</h1>
                </div>
                <span className={`amadeus-channel-state is-${chat.connectionState}`}>
                  <i />
                  {chat.connectionState === 'online' ? '通道已接通' : chat.connectionState === 'connecting' ? '正在接通' : '通道离线'}
                </span>
              </div>

              <div className="amadeus-messages" aria-live="polite">
                {chat.messages.length === 0 && (
                  <div className="amadeus-empty-chat">
                    <Sparkles aria-hidden="true" />
                    <strong>{chatEnabled ? '这里很安静。' : '还不能开始对话。'}</strong>
                    <p>
                      {chatEnabled
                        ? '发一条消息，桌面与 QQ 会共享同一个“你”和同一份长期记忆。'
                        : !remoteReady
                          ? '云端千惠上线后，对话通道会自动恢复。'
                          : '在连接设置里映射你的身份后，就可以开始。'}
                    </p>
                  </div>
                )}
                {chat.messages.map((message) => (
                  <article key={message.id} className={`amadeus-message is-${message.role}`}>
                    <span>{message.role === 'assistant' ? '千惠' : '你'} · {formatTime(message.createdAt)}</span>
                    <p>{message.content}</p>
                  </article>
                ))}
                {chat.awaitingReply && (
                  <div className="amadeus-thinking" aria-label="千惠正在思考"><i /><i /><i /></div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {(chat.error || (!identityReady && remoteReady)) && (
                <div className="amadeus-chat-hint">
                  {chat.error || '需要先完成主人身份映射'}
                  <button onClick={() => setSettingsOpen(true)}>打开连接设置</button>
                </div>
              )}

              <div className="amadeus-composer">
                <textarea
                  value={messageInput}
                  onChange={(event) => setMessageInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                      event.preventDefault()
                      handleSend()
                    }
                  }}
                  placeholder={chat.connectionState === 'online' ? '对千惠说些什么…' : '等待对话通道接通…'}
                  disabled={chat.connectionState !== 'online'}
                  rows={2}
                />
                <button
                  onClick={handleSend}
                  disabled={!messageInput.trim() || chat.connectionState !== 'online'}
                  aria-label="发送消息"
                >
                  <Send />
                </button>
              </div>
            </section>

            <aside className="amadeus-activity-panel">
              <section className="amadeus-approval-section">
                <div className="amadeus-side-heading">
                  <div>
                    <span className="amadeus-eyebrow">CONSENT GATE</span>
                    <h2>需要你确认</h2>
                  </div>
                  <ShieldCheck />
                </div>
                {pendingCommands.length === 0 ? (
                  <div className="amadeus-clear-state">
                    <Check />
                    <span>没有等待中的动作</span>
                  </div>
                ) : pendingCommands.map((command) => (
                  <ApprovalCard
                    key={command.id}
                    command={command}
                    busy={decisionBusy === command.id}
                    onDecision={handleDecision}
                  />
                ))}
              </section>

              <section className="amadeus-events-section">
                <div className="amadeus-side-heading">
                  <div>
                    <span className="amadeus-eyebrow">RECENT SIGNALS</span>
                    <h2>最近发生</h2>
                  </div>
                  <MessageCircle />
                </div>
                <div className="amadeus-event-list">
                  {events.length === 0 ? (
                    <p className="amadeus-empty-events">还没有事件。连接变化和重要动作会出现在这里。</p>
                  ) : events.slice(0, 12).map((event) => (
                    <div key={event.id} className={`amadeus-event is-${event.status}`}>
                      <i />
                      <div>
                        <span>{formatTime(event.created_at)}</span>
                        <strong>{eventTitle(event)}</strong>
                        {event.summary && <p>{event.summary}</p>}
                      </div>
                      <button onClick={() => void handleDeleteEvent(event.id)} aria-label="删除这条记录">
                        <Trash2 />
                      </button>
                    </div>
                  ))}
                </div>
              </section>
            </aside>
          </div>
        )}
      </main>

      {settingsOpen && (
        <ConnectionSettings
          currentStatus={status}
          onClose={() => setSettingsOpen(false)}
          onSaved={async () => {
            setSettingsOpen(false)
            await refresh()
          }}
        />
      )}
    </div>
  )
}

function LifeNode({ label, detail, active }: { label: string; detail: string; active: boolean }) {
  return (
    <div className={`amadeus-life-node ${active ? 'is-active' : ''}`}>
      <span><i /></span>
      <div><strong>{label}</strong><small>{detail}</small></div>
    </div>
  )
}

function CapabilityButton({
  icon: Icon,
  label,
  detail,
  active = false,
  busy = false,
  disabled = false,
  onClick,
}: {
  icon: LucideIcon
  label: string
  detail: string
  active?: boolean
  busy?: boolean
  disabled?: boolean
  onClick?: () => void
}) {
  return (
    <button className={`amadeus-capability ${active ? 'is-active' : ''}`} disabled={disabled || busy} onClick={onClick}>
      <Icon />
      <span><strong>{label}</strong><small>{busy ? '请稍候…' : detail}</small></span>
      <i className="amadeus-capability-switch" />
    </button>
  )
}

function ApprovalCard({
  command,
  busy,
  onDecision,
}: {
  command: AmadeusCommand
  busy: boolean
  onDecision: (id: string, approved: boolean) => Promise<void>
}) {
  const detail = Object.entries(command.payload)
    .slice(0, 2)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(' · ')
  return (
    <article className="amadeus-approval-card">
      <div className="amadeus-approval-title">
        <AlertTriangle />
        <div><strong>{ACTION_LABELS[command.action] || command.action}</strong><span>{formatTime(command.created_at)}</span></div>
      </div>
      {detail && <p>{detail}</p>}
      <div className="amadeus-approval-actions">
        <button disabled={busy} onClick={() => void onDecision(command.id, false)}>拒绝</button>
        <button disabled={busy} className="is-primary" onClick={() => void onDecision(command.id, true)}>
          {busy ? '处理中…' : '允许这一次'}
        </button>
      </div>
    </article>
  )
}

function BackendOffline({ onRetry }: { onRetry: () => void }) {
  const [copied, setCopied] = useState(false)
  const command = 'uv run python -m src.amadeus'
  return (
    <section className="amadeus-backend-offline">
      <div className="amadeus-offline-orbit"><WifiOff /><i /><i /></div>
      <span className="amadeus-eyebrow">LOCAL CORE OFFLINE</span>
      <h1>本机中枢还没有醒来</h1>
      <p>Amadeus 前端已经就绪，但无法连接 `127.0.0.1:8765`。在项目目录运行下面的命令。</p>
      <button
        className="amadeus-command-copy"
        onClick={async () => {
          await navigator.clipboard.writeText(command)
          setCopied(true)
          window.setTimeout(() => setCopied(false), 1600)
        }}
      >
        <code>{command}</code><span>{copied ? '已复制' : '复制命令'}</span>
      </button>
      <button className="amadeus-retry-button" onClick={onRetry}><RefreshCw />重新连接</button>
    </section>
  )
}

function ConnectionSettings({
  currentStatus,
  onClose,
  onSaved,
}: {
  currentStatus: AmadeusStatus | null
  onClose: () => void
  onSaved: () => Promise<void>
}) {
  const [config, setConfig] = useState<RemoteConfig | null>(null)
  const [remoteUrl, setRemoteUrl] = useState('http://127.0.0.1:18001')
  const [token, setToken] = useState('')
  const [personId, setPersonId] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    amadeusApi.remoteConfig().then((loaded) => {
      setConfig(loaded)
      if (loaded.remote_base_url) setRemoteUrl(loaded.remote_base_url)
      if (loaded.owner_person_id) setPersonId(loaded.owner_person_id)
    }).catch((cause) => setError(cause instanceof Error ? cause.message : '无法读取连接设置'))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      await amadeusApi.updateRemoteConfig({
        remote_base_url: remoteUrl.trim(),
        remote_token: token.trim(),
        owner_person_id: personId.trim(),
      })
      await onSaved()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="amadeus-modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <section className="amadeus-settings-dialog" role="dialog" aria-modal="true" aria-labelledby="connection-title">
        <div className="amadeus-settings-header">
          <div><span className="amadeus-eyebrow">CONNECTION</span><h2 id="connection-title">连接云端千惠</h2></div>
          <button onClick={onClose} aria-label="关闭连接设置"><X /></button>
        </div>
        <div className="amadeus-settings-status">
          <i className={currentStatus?.remote.online ? 'is-online' : ''} />
          <span>{currentStatus?.remote.online ? '当前连接正常' : '当前未连接'}</span>
          {currentStatus?.identity.mapped && <small>已映射为 {currentStatus.identity.display_name}</small>}
        </div>
        <label>
          <span>云端地址</span>
          <input value={remoteUrl} onChange={(event) => setRemoteUrl(event.target.value)} placeholder="http://127.0.0.1:18001" />
          <small>推荐使用 SSH 隧道或 HTTPS，不要让独立 token 经过公网明文 HTTP。</small>
        </label>
        <label>
          <span>Amadeus 独立 token</span>
          <input value={token} onChange={(event) => setToken(event.target.value)} type="password" placeholder={config?.remote_token_configured ? '已保存；修改时请重新输入 64 位 token' : '输入 64 位 token'} />
        </label>
        <label>
          <span>你的 person_id</span>
          <input value={personId} onChange={(event) => setPersonId(event.target.value)} placeholder="用于共享人物资料与长期记忆" />
        </label>
        {error && <p className="amadeus-settings-error">{error}</p>}
        <div className="amadeus-settings-actions">
          <button onClick={onClose}>取消</button>
          <button className="is-primary" disabled={saving || !remoteUrl.trim() || token.trim().length !== 64 || !personId.trim()} onClick={() => void handleSave()}>
            {saving ? '正在连接…' : '保存并连接'}<ChevronRight />
          </button>
        </div>
      </section>
    </div>
  )
}
