import { useEffect, useMemo, useRef, useState } from 'react'

import { getAmadeusWebSocketUrl } from '@/lib/amadeus-api'

export type AmadeusMindConnectionState = 'connecting' | 'online' | 'offline'

export interface AmadeusMindEvent {
  id: string
  type: string
  data: Record<string, unknown>
  timestamp: number
  sessionId: string
  sessionName: string
}

export interface AmadeusMindStage {
  sessionId: string
  sessionName: string
  stage: string
  detail: string
  roundText: string
  agentState: string
  updatedAt: number
}

const DISPLAYED_EVENT_TYPES = new Set([
  'message.ingested',
  'message.sent',
  'cycle.start',
  'timing_gate.result',
  'planner.response',
  'planner.finalized',
  'tool.execution',
  'cycle.end',
  'replier.response',
])

function toStage(data: Record<string, unknown>): AmadeusMindStage | null {
  const sessionId = typeof data.session_id === 'string' ? data.session_id : ''
  if (!sessionId) return null
  return {
    sessionId,
    sessionName: typeof data.session_name === 'string' ? data.session_name : sessionId.slice(0, 8),
    stage: typeof data.stage === 'string' ? data.stage : '等待',
    detail: typeof data.detail === 'string' ? data.detail : '',
    roundText: typeof data.round_text === 'string' ? data.round_text : '',
    agentState: typeof data.agent_state === 'string' ? data.agent_state : '',
    updatedAt: typeof data.updated_at === 'number' ? data.updated_at * 1000 : Date.now(),
  }
}

export function useAmadeusMind(enabled: boolean) {
  const [events, setEvents] = useState<AmadeusMindEvent[]>([])
  const [stageMap, setStageMap] = useState<Map<string, AmadeusMindStage>>(new Map())
  const [connectionState, setConnectionState] = useState<AmadeusMindConnectionState>('offline')
  const [error, setError] = useState('')
  const socketRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)

  useEffect(() => {
    if (!enabled) return
    let disposed = false

    const connect = () => {
      if (disposed) return
      setConnectionState('connecting')
      const socket = new WebSocket(getAmadeusWebSocketUrl())
      socketRef.current = socket

      socket.onopen = () => {
        setConnectionState('online')
        setError('')
        socket.send(JSON.stringify({
          op: 'subscribe',
          id: crypto.randomUUID(),
          domain: 'maisaka_monitor',
          topic: 'main',
        }))
      }

      socket.onmessage = (event) => {
        let envelope: Record<string, unknown>
        try {
          envelope = JSON.parse(String(event.data)) as Record<string, unknown>
        } catch {
          return
        }

        if (envelope.op === 'response' && envelope.ok === false) {
          const responseError = envelope.error
          const message = responseError && typeof responseError === 'object'
            ? String((responseError as Record<string, unknown>).message || '')
            : ''
          setError(message || '心理活动订阅失败')
          return
        }
        if (envelope.op !== 'event' || envelope.domain !== 'maisaka_monitor') return

        const rawData = envelope.data
        if (!rawData || typeof rawData !== 'object') return
        const data = rawData as Record<string, unknown>
        const eventType = String(envelope.event || '')

        if (eventType === 'stage.snapshot') {
          const entries = data.entries
          if (!Array.isArray(entries)) return
          const nextStages = new Map<string, AmadeusMindStage>()
          for (const entry of entries) {
            if (!entry || typeof entry !== 'object') continue
            const stage = toStage(entry as Record<string, unknown>)
            if (stage) nextStages.set(stage.sessionId, stage)
          }
          setStageMap(nextStages)
          return
        }

        if (eventType === 'stage.status') {
          const stage = toStage(data)
          if (!stage) return
          setStageMap((current) => {
            const next = new Map(current)
            next.set(stage.sessionId, stage)
            return next
          })
          return
        }

        if (eventType === 'stage.removed') {
          const sessionId = typeof data.session_id === 'string' ? data.session_id : ''
          if (!sessionId) return
          setStageMap((current) => {
            const next = new Map(current)
            next.delete(sessionId)
            return next
          })
          return
        }

        if (!DISPLAYED_EVENT_TYPES.has(eventType)) return
        const timestamp = typeof data.timestamp === 'number' ? data.timestamp * 1000 : Date.now()
        const sessionId = typeof data.session_id === 'string' ? data.session_id : ''
        const sessionName = typeof data.session_name === 'string'
          ? data.session_name
          : sessionId.slice(0, 8) || '未知聊天流'
        setEvents((current) => [...current, {
          id: `${eventType}-${crypto.randomUUID()}`,
          type: eventType,
          data,
          timestamp,
          sessionId,
          sessionName,
        }].slice(-160))
      }

      socket.onerror = () => setError('无法连接千惠的心理活动通道')
      socket.onclose = () => {
        if (socketRef.current === socket) socketRef.current = null
        setConnectionState('offline')
        if (!disposed) reconnectTimerRef.current = window.setTimeout(connect, 3000)
      }
    }

    connect()
    return () => {
      disposed = true
      if (reconnectTimerRef.current) window.clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [enabled])

  const stages = useMemo(
    () => [...stageMap.values()].sort((left, right) => right.updatedAt - left.updatedAt),
    [stageMap],
  )

  return {
    events,
    stages,
    connectionState: enabled ? connectionState : 'offline' as const,
    error,
  }
}
