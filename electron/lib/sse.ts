/**
 * SSE 流解析（architecture.md 2.2）。
 * 事件统一形态：`{stage, percent, message, extra?}`。
 */

export interface ProgressEvent {
  stage: string
  percent: number
  message: string
  extra?: Record<string, unknown>
}

export const TERMINAL_STAGES = ['completed', 'failed', 'cancelled'] as const

export function isTerminalStage(stage: string): boolean {
  return (TERMINAL_STAGES as readonly string[]).includes(stage)
}

/**
 * 从 SSE 响应中逐条解析 `data:` 行的 JSON 负载。
 * 忽略空行、注释（`: `）与 `event:`/`id:` 等其他字段。
 */
export async function* parseSSE(response: Response): AsyncGenerator<ProgressEvent> {
  if (!response.body) {
    throw new Error('响应无 body，无法解析 SSE')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  for await (const chunk of response.body as AsyncIterable<Uint8Array>) {
    buffer += decoder.decode(chunk, { stream: true })

    let separator: number
    while ((separator = buffer.indexOf('\n\n')) >= 0) {
      const rawEvent = buffer.slice(0, separator)
      buffer = buffer.slice(separator + 2)

      for (const line of rawEvent.split('\n')) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue
        const data = trimmed.slice(5).trim()
        if (data) {
          yield JSON.parse(data) as ProgressEvent
        }
      }
    }
  }
}
