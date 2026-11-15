import { describe, expect, it, vi } from 'vitest'
import { chatEnter } from './chatKeyboard'

describe('chat composer keyboard', () => {
  const key = (changes = {}) => ({ key: 'Enter', shiftKey: false, isComposing: false, keyCode: 13, repeat: false, preventDefault: vi.fn(), ...changes } as unknown as KeyboardEvent)
  it('sends once and prevents the textarea newline', () => {
    const send = vi.fn(), event = key()
    chatEnter(event, send)
    expect(send).toHaveBeenCalledOnce()
    expect(event.preventDefault).toHaveBeenCalledOnce()
  })
  it.each([{ shiftKey: true }, { isComposing: true }, { keyCode: 229 }, { key: 'a' }])('keeps newline or IME input: %o', changes => {
    const send = vi.fn(), event = key(changes)
    chatEnter(event, send)
    expect(send).not.toHaveBeenCalled()
    expect(event.preventDefault).not.toHaveBeenCalled()
  })
  it('does not send when holding Enter', () => {
    const send = vi.fn(), event = key({ repeat: true })
    chatEnter(event, send)
    expect(send).not.toHaveBeenCalled()
    expect(event.preventDefault).toHaveBeenCalledOnce()
  })
})
