/** IME confirmation (including Safari's legacy 229) must never send a message. */
export function chatEnter(event: KeyboardEvent, send: () => unknown) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  if (!event.repeat) void send()
}
