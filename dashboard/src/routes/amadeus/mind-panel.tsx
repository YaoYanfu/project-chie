import { useEffect, useRef } from 'react'
import {
  Activity,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Eye,
  MessageSquareText,
  Wrench,
} from 'lucide-react'

import type { AmadeusMindEvent, AmadeusMindStage } from './use-amadeus-mind'

interface MindDescription {
  title: string
  detail: string
  kind: 'observe' | 'think' | 'act' | 'reply' | 'settle'
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export function describeMindEvent(event: AmadeusMindEvent): MindDescription {
  const data = event.data
  switch (event.type) {
    case 'message.ingested':
      return {
        title: `注意到 ${asText(data.speaker_name) || '新消息'}`,
        detail: asText(data.content),
        kind: 'observe',
      }
    case 'cycle.start':
      return {
        title: '开始整理刚刚发生的事',
        detail: `第 ${Number(data.round_index || 0) + 1} 轮 · 参考 ${Number(data.history_count || 0)} 条上下文`,
        kind: 'think',
      }
    case 'timing_gate.result': {
      const action = asText(data.action)
      const labels: Record<string, string> = {
        continue: '决定继续想一想',
        wait: '决定先等一等',
        no_action: '决定暂时不回应',
      }
      return {
        title: labels[action] || '判断现在是否需要回应',
        detail: asText(data.content),
        kind: 'think',
      }
    }
    case 'planner.response':
      return {
        title: '形成了下一步想法',
        detail: asText(data.content),
        kind: 'think',
      }
    case 'planner.finalized': {
      const planner = asRecord(data.planner)
      const finalState = asRecord(data.final_state)
      return {
        title: data.interrupted ? '这次思考被新消息打断' : '想清楚接下来怎么做了',
        detail: asText(planner.content) || asText(finalState.end_detail),
        kind: data.interrupted ? 'settle' : 'think',
      }
    }
    case 'tool.execution':
      return {
        title: `${data.success === false ? '尝试调用' : '调用'} ${asText(data.tool_name) || '工具'}`,
        detail: asText(data.result_summary),
        kind: 'act',
      }
    case 'replier.response':
      return {
        title: data.success === false ? '组织回复时遇到了问题' : '正在组织要说的话',
        detail: asText(data.reasoning) || asText(data.content),
        kind: 'reply',
      }
    case 'message.sent':
      return {
        title: '已经把想说的话发出去了',
        detail: asText(data.content),
        kind: 'reply',
      }
    case 'cycle.end':
      return {
        title: '这一轮思考结束',
        detail: asText(data.end_detail),
        kind: 'settle',
      }
    default:
      return { title: event.type, detail: '', kind: 'settle' }
  }
}

function MindIcon({ kind }: { kind: MindDescription['kind'] }) {
  if (kind === 'observe') return <Eye />
  if (kind === 'act') return <Wrench />
  if (kind === 'reply') return <MessageSquareText />
  if (kind === 'settle') return <CheckCircle2 />
  return <BrainCircuit />
}

function formatMindTime(timestamp: number): string {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(timestamp)
}

function MindStageCard({ stage }: { stage: AmadeusMindStage }) {
  return (
    <article className="amadeus-mind-stage">
      <span className="amadeus-mind-stage-pulse"><i /></span>
      <div>
        <small>{stage.sessionName}</small>
        <strong>{stage.stage || '正在思考'}</strong>
        {(stage.detail || stage.roundText) && (
          <p>{[stage.detail, stage.roundText].filter(Boolean).join(' · ')}</p>
        )}
      </div>
      {stage.agentState && <em>{stage.agentState}</em>}
    </article>
  )
}

export function AmadeusMindPanel({
  events,
  stages,
  error,
}: {
  events: AmadeusMindEvent[]
  stages: AmadeusMindStage[]
  error: string
}) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  return (
    <div className="amadeus-mind-panel">
      <section className="amadeus-mind-now" aria-label="千惠当前状态">
        <div className="amadeus-mind-section-label">
          <Activity />
          <span>此刻</span>
          <small>{stages.length > 0 ? `${stages.length} 条活跃聊天流` : '等待新的念头'}</small>
        </div>
        <div className="amadeus-mind-stage-list">
          {stages.length > 0
            ? stages.map((stage) => <MindStageCard key={stage.sessionId} stage={stage} />)
            : <p className="amadeus-mind-stage-empty">千惠现在没有正在处理的消息。</p>}
        </div>
      </section>

      <section className="amadeus-mind-stream" aria-label="千惠心理活动时间线">
        <div className="amadeus-mind-section-label">
          <Clock3 />
          <span>意识流</span>
          <small>仅展示判断、规划、工具与回复过程</small>
        </div>
        {error && <div className="amadeus-mind-error">{error}</div>}
        {events.length === 0 ? (
          <div className="amadeus-mind-empty">
            <BrainCircuit />
            <strong>还没有新的心理活动</strong>
            <p>当千惠收到消息或主动开始思考时，过程会实时出现在这里。</p>
          </div>
        ) : (
          <div className="amadeus-mind-timeline">
            {events.map((event) => {
              const description = describeMindEvent(event)
              return (
                <article key={event.id} className={`amadeus-mind-entry is-${description.kind}`}>
                  <div className="amadeus-mind-entry-icon"><MindIcon kind={description.kind} /></div>
                  <div className="amadeus-mind-entry-body">
                    <div>
                      <span>{event.sessionName}</span>
                      <time>{formatMindTime(event.timestamp)}</time>
                    </div>
                    <strong>{description.title}</strong>
                    {description.detail && <p>{description.detail}</p>}
                  </div>
                </article>
              )
            })}
            <div ref={endRef} />
          </div>
        )}
      </section>
    </div>
  )
}
