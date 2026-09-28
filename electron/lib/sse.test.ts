import type { ProgressEvent } from './sse'
import { describe, expect, it } from 'vitest'
import { isTerminalStage, parseSSE } from './sse'

function responseFromChunks(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  return new Response(stream, { status: 200 })
}

async function collect(response: Response): Promise<ProgressEvent[]> {
  const events: ProgressEvent[] = []
  for await (const event of parseSSE(response)) {
    events.push(event)
  }
  return events
}

describe('parseSSE', () => {
  it('解析 data 行、忽略注释/event 字段，分片任意切割均可重组', async () => {
    const raw =
      'event: progress\n' +
      'data: {"stage":"queued","percent":0,"message":"任务已创建"}\n\n' +
      ': a comment line\n' +
      '\n' +
      'data: {"stage":"completed","percent":100,"message":"完成","extra":{"k":"v"}}\n\n'

    // 逐字符分片，强制走缓冲拼接路径
    const events = await collect(responseFromChunks(raw.split('')))

    expect(events).toHaveLength(2)
    expect(events[0]).toMatchObject({ stage: 'queued', percent: 0 })
    expect(events[1]).toMatchObject({ stage: 'completed', percent: 100 })
    expect(events[1].extra).toEqual({ k: 'v' })
  })

  it('响应无 body 时抛错', async () => {
    await expect(collect(new Response(null, { status: 200 }))).rejects.toThrow(/body/)
  })

  it('非法 JSON 向上抛出，不静默吞掉', async () => {
    await expect(collect(responseFromChunks(['data: {not-json}\n\n']))).rejects.toBeTruthy()
  })
})

describe('isTerminalStage', () => {
  it('终态识别准确', () => {
    expect(isTerminalStage('completed')).toBe(true)
    expect(isTerminalStage('failed')).toBe(true)
    expect(isTerminalStage('cancelled')).toBe(true)
    expect(isTerminalStage('progress')).toBe(false)
  })
})
