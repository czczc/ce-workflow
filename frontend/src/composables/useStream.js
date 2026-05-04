/**
 * Consume an SSE response body and dispatch events to handlers by type.
 * @param {Response} resp - fetch Response with a readable SSE body
 * @param {Record<string, (evt: object) => void>} handlers - map of event type → handler
 */
export async function readStream(resp, handlers) {
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop()
    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6)
      if (data === '[DONE]') return
      const evt = JSON.parse(data)
      handlers[evt.type]?.(evt)
    }
  }
}
