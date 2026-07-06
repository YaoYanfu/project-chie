import { useCallback, useEffect, useRef, useState } from 'react'

import { getAmadeusWebSocketUrl } from '@/lib/amadeus-api'

export interface AmadeusChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: number
}

type ConnectionState = 'connecting' | 'online' | 'offline'

const SESSION_ID = 'amadeus-desktop'

function historyToMessages(rawMessages: unknown[]): AmadeusChatMessage[] {
  return rawMessages.flatMap((entry, index) => {
    if (!entry || typeof entry !== 'object') return []
    const message = entry as Record<string, unknown>
    const content = String(message.content || '').trim()
    if (!content) return []
    return [{
      id: String(message.id || `history-${index}`),
      role: message.is_bot || message.type === 'bot' ? 'assistant' as const : 'user' as const,
      content,
      createdAt: Number(message.timestamp || Date.now() / 1000) * 1000,
    }]
  })
}

function buildCall(method: string, data: Record<string, unknown> = {}) {
  return {
    op: 'call',
    id: crypto.randomUUID(),
    domain: 'chat',
    method,
    session: SESSION_ID,
    data,
  }
}

export function useAmadeusChat(enabled: boolean) {
  const [messages, setMessages] = useState<AmadeusChatMessage[]>([])
  const [connectionState, setConnectionState] = useState<ConnectionState>('offline')
  const [awaitingReply, setAwaitingReply] = useState(false)
  const [error, setError] = useState('')
  const socketRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const manuallyClosedRef = useRef(false)

  useEffect(() => {
    if (!enabled) return

    manuallyClosedRef.current = false

    const connect = () => {
      setConnectionState('connecting')
      const socket = new WebSocket(getAmadeusWebSocketUrl())
      socketRef.current = socket

      socket.onopen = () => {
        setConnectionState('online')
        setError('')
        socket.send(JSON.stringify(buildCall('session.open', { user_name: '主人', restore: true })))
      }

      socket.onmessage = (event) => {
        let envelope: Record<string, unknown>
        try {
          envelope = JSON.parse(String(event.data)) as Record<string, unknown>
        } catch {
          return
        }

        if (envelope.type === 'error') {
          setError(String(envelope.message || '聊天连接异常'))
          return
        }
        if (envelope.op !== 'event' || envelope.domain !== 'chat') return

        const data = envelope.data
        if (!data || typeof data !== 'object') return
        const chatEvent = data as Record<string, unknown>
        const type = String(chatEvent.type || envelope.event || '')

        if (type === 'history' && Array.isArray(chatEvent.messages)) {
          setMessages(historyToMessages(chatEvent.messages))
          return
        }
        if (type !== 'bot_message' && type !== 'assistant_message') return

        const content = String(chatEvent.content || '').trim()
        if (!content) return
        setMessages((current) => [...current, {
          id: String(chatEvent.id || `assistant-${Date.now()}`),
          role: 'assistant',
          content,
          createdAt: Date.now(),
        }])
        setAwaitingReply(false)
      }

      socket.onerror = () => {
        setError('本机 Amadeus 无法建立聊天通道')
      }

      socket.onclose = () => {
        if (socketRef.current === socket) socketRef.current = null
        setConnectionState('offline')
        setAwaitingReply(false)
        if (!manuallyClosedRef.current) {
          reconnectTimerRef.current = window.setTimeout(connect, 3000)
        }
      }
    }

    connect()
    return () => {
      manuallyClosedRef.current = true
      if (reconnectTimerRef.current) window.clearTimeout(reconnectTimerRef.current)
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [enabled])

  const sendMessage = useCallback((content: string) => {
    const text = content.trim()
    const socket = socketRef.current
    if (!text || !socket || socket.readyState !== WebSocket.OPEN) return false

    setMessages((current) => [...current, {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      createdAt: Date.now(),
    }])
    setAwaitingReply(true)
    socket.send(JSON.stringify(buildCall('message.send', { content: text, user_name: '主人' })))
    return true
  }, [])

  return {
    messages,
    connectionState: enabled ? connectionState : 'offline',
    awaitingReply,
    error,
    sendMessage,
  }
}
