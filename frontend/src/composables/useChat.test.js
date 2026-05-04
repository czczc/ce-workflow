import { describe, it, expect } from 'vitest'
import { createChatSession, useSharedSession } from './useChat.js'

describe('createChatSession', () => {
  it('returns independent state on each call', () => {
    const a = createChatSession()
    const b = createChatSession()

    a.messages.value.push({ role: 'user', text: 'hello' })

    expect(b.messages.value).toHaveLength(0)
    expect(a.messages.value).toHaveLength(1)
  })

  it('initializes with empty/default values', () => {
    const session = createChatSession()
    expect(session.messages.value).toEqual([])
    expect(session.streaming.value).toBe(false)
    expect(session.activeNode.value).toBeNull()
    expect(session.completedNodes.value.size).toBe(0)
  })
})

describe('useSharedSession', () => {
  it('returns the same instance on repeated calls', () => {
    const a = useSharedSession()
    const b = useSharedSession()
    expect(a).toBe(b)
  })
})
