import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, MessageCircle, RotateCw, Send, Wifi, WifiOff } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { chatWsClient } from '@/lib/chat-ws-client'
import { unifiedWsClient } from '@/lib/unified-ws'

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  id: string
  ts: number
}

const SESSION_ID = 'amadeus_desktop'
const STORAGE_KEY = 'amadeus_chat_history'

function loadHistory(): ChatMsg[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.slice(-200) // 最多保留 200 条
  } catch { return [] }
}

function saveHistory(msgs: ChatMsg[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(msgs.slice(-200)))
  } catch { /* localStorage 满了就放弃 */ }
}

export function AmadeusChat() {
  const [messages, setMessages] = useState<ChatMsg[]>(loadHistory)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [connected, setConnected] = useState(false)
  const navigate = useNavigate()
  const bottomRef = useRef<HTMLDivElement>(null)

  const scrollDown = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    unifiedWsClient.connect()

    const unsubConn = unifiedWsClient.onConnectionChange((ok: boolean) => setConnected(ok))

    const unsubMsg = chatWsClient.onSessionMessage(SESSION_ID, (data: Record<string, unknown>) => {
      if (data.type === 'bot_message' || data.type === 'assistant_message') {
        const content = String(data.content || '')
        if (content) {
          setMessages(prev => {
            const next = [...prev, { role: 'assistant' as const, content, id: `b_${Date.now()}`, ts: Date.now() }]
            saveHistory(next)
            return next
          })
          setSending(false)
        }
      }
    })

    chatWsClient.openSession(SESSION_ID, {
      platform: 'qq',
      person_id: 'af7920b7072442a7f042cf34d7fd0995',
      group_id: 'webui_virtual_group_qq_3471856914',
      group_name: 'Amadeus 虚拟群聊',
      user_name: 'yves',
    }).catch(console.error)

    return () => {
      unsubConn()
      unsubMsg()
      chatWsClient.closeSession(SESSION_ID).catch(() => {})
    }
  }, [])

  useEffect(() => { scrollDown() }, [messages, scrollDown])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || sending || !connected) return
    setInput('')
    setSending(true)

    const userMsg: ChatMsg = { role: 'user', content: text, id: `u_${Date.now()}`, ts: Date.now() }
    setMessages(prev => { const n = [...prev, userMsg]; saveHistory(n); return n })

    try {
      await chatWsClient.sendMessage(SESSION_ID, text, 'yves')
    } catch (err) {
      console.error('发送失败:', err)
      setSending(false)
    }
  }, [input, sending, connected])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      send()
    }
  }, [send])

  const handleClearHistory = useCallback(() => {
    setMessages([])
    saveHistory([])
  }, [])

  return (
    <div className="h-full flex flex-col bg-[#0d0b10] text-white">
      {/* 顶栏 */}
      <div className="shrink-0 flex items-center gap-3 px-4 py-3 border-b border-white/10 bg-white/5">
        <button
          onClick={() => navigate({ to: '/amadeus' })}
          className="text-white/50 hover:text-white/80 transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-sm">与千惠对话</h2>
          {connected ? <Wifi className="h-3.5 w-3.5 text-emerald-400" /> : <WifiOff className="h-3.5 w-3.5 text-red-400" />}
        </div>
        <div className="flex-1" />
        {messages.length > 0 && (
          <button
            onClick={handleClearHistory}
            className="text-white/25 hover:text-white/50 text-xs transition-colors px-2 py-1 rounded"
          >
            清空记录
          </button>
        )}
        <p className="text-white/35 text-xs">{connected ? '在线 · 共享记忆' : '等待连接…'}</p>
      </div>

      {/* 消息区 */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-white/25 text-sm">
            <div className="text-center space-y-2">
              <MessageCircle className="h-10 w-10 mx-auto opacity-30" />
              <p>和千惠说点什么</p>
            </div>
          </div>
        )}
        {messages.map(msg => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
              msg.role === 'user'
                ? 'bg-teal-600/30 border border-teal-500/20 text-white/90'
                : 'bg-white/10 border border-white/10 text-white/85'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-white/5 border border-white/10 rounded-2xl px-4 py-3">
              <RotateCw className="h-4 w-4 text-white/30 animate-spin" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 输入区 */}
      <div className="shrink-0 border-t border-white/10 bg-white/5 p-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="对千惠说话… Enter 发送"
            rows={2}
            className="flex-1 resize-none rounded-xl bg-white/5 border border-white/10 px-4 py-2.5 text-sm text-white placeholder:text-white/25 focus:outline-none focus:border-rose-500/40 focus:ring-2 focus:ring-rose-500/10"
            disabled={sending || !connected}
          />
          <Button
            onClick={send}
            disabled={sending || !input.trim() || !connected}
            className="shrink-0 bg-rose-600 hover:bg-rose-500 text-white h-10 w-10 p-0 rounded-xl"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
