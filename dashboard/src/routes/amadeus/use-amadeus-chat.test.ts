import { describe, expect, it } from 'vitest'

import {
  historyToMessages,
  mergeChatMessages,
  type AmadeusChatMessage,
} from './use-amadeus-chat'

const current: AmadeusChatMessage[] = [{
  id: 'optimistic-user',
  role: 'user',
  content: '你好',
  createdAt: 10_000,
}]

describe('Amadeus 聊天历史合并', () => {
  it('远端返回空历史时保留当前消息', () => {
    expect(mergeChatMessages(current, [])).toBe(current)
  })

  it('用云端正式消息替换内容和时间接近的乐观消息', () => {
    const merged = mergeChatMessages(current, [{
      id: 'remote-user',
      role: 'user',
      content: '你好',
      createdAt: 12_000,
    }])

    expect(merged).toEqual([{
      id: 'remote-user',
      role: 'user',
      content: '你好',
      createdAt: 12_000,
    }])
  })

  it('识别云端 message_id 并正确转换机器人角色', () => {
    expect(historyToMessages([{
      message_id: 'bot-1',
      type: 'bot',
      content: '我在',
      timestamp: 20,
    }])).toEqual([{
      id: 'bot-1',
      role: 'assistant',
      content: '我在',
      createdAt: 20_000,
    }])
  })
})
