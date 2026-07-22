import { describe, expect, it } from 'vitest'

import { describeMindEvent } from './mind-panel'
import type { AmadeusMindEvent } from './use-amadeus-mind'

function event(type: string, data: Record<string, unknown>): AmadeusMindEvent {
  return {
    id: 'event-1',
    type,
    data,
    timestamp: 1,
    sessionId: 'session-1',
    sessionName: '测试聊天流',
  }
}

describe('Amadeus 心理活动文案', () => {
  it('展示 planner 的想法但不暴露请求上下文', () => {
    const description = describeMindEvent(event('planner.finalized', {
      planner: { content: '先确认对方真正想问什么' },
      request: { messages: [{ content: '敏感上下文' }] },
      final_state: {},
    }))

    expect(description.title).toBe('想清楚接下来怎么做了')
    expect(description.detail).toBe('先确认对方真正想问什么')
    expect(description.detail).not.toContain('敏感上下文')
  })

  it('把工具执行转换成容易理解的活动', () => {
    expect(describeMindEvent(event('tool.execution', {
      tool_name: 'weather',
      result_summary: '已经获得天气信息',
      success: true,
    }))).toMatchObject({
      title: '调用 weather',
      detail: '已经获得天气信息',
      kind: 'act',
    })
  })
})
