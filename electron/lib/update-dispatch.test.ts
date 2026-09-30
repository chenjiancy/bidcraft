import { EventEmitter } from 'node:events'
import { describe, expect, it, vi } from 'vitest'
import { registerUpdaterEvents } from './update-dispatch'

type SendLog = { channel: string; payload?: unknown }

function makeSender() {
  const logs: SendLog[] = []
  const send = vi.fn((channel: string, payload?: unknown) => {
    logs.push({ channel, payload })
  })
  return { send, logs }
}

function makeEmitter() {
  const emitter = new EventEmitter()
  const on = vi.fn(emitter.on.bind(emitter))
  return { emitter, on }
}

describe('registerUpdaterEvents', () => {
  it('向 autoUpdater 注册全部 6 个事件监听', () => {
    const { on } = makeEmitter()
    const { send } = makeSender()
    registerUpdaterEvents({ on } as never, send)
    expect(on).toHaveBeenCalledTimes(6)
    expect(on.mock.calls.map((c) => c[0])).toContain('checking-for-update')
    expect(on.mock.calls.map((c) => c[0])).toContain('update-available')
    expect(on.mock.calls.map((c) => c[0])).toContain('update-not-available')
    expect(on.mock.calls.map((c) => c[0])).toContain('download-progress')
    expect(on.mock.calls.map((c) => c[0])).toContain('update-downloaded')
    expect(on.mock.calls.map((c) => c[0])).toContain('error')
  })

  it('checking-for-update → update:status { status: "checking" }', () => {
    const { emitter } = makeEmitter()
    const { send, logs } = makeSender()
    registerUpdaterEvents(emitter as never, send)

    emitter.emit('checking-for-update')
    expect(logs).toHaveLength(1)
    expect(logs[0]).toEqual({ channel: 'update:status', payload: { status: 'checking' } })
  })

  it('update-available → update:status { status: "available" }', () => {
    const { emitter } = makeEmitter()
    const { send, logs } = makeSender()
    registerUpdaterEvents(emitter as never, send)
    emitter.emit('update-available')
    expect(logs).toEqual([{ channel: 'update:status', payload: { status: 'available' } }])
  })

  it('update-not-available → update:status { status: "not_available" }', () => {
    const { emitter } = makeEmitter()
    const { send, logs } = makeSender()
    registerUpdaterEvents(emitter as never, send)
    emitter.emit('update-not-available')
    expect(logs).toEqual([{ channel: 'update:status', payload: { status: 'not_available' } }])
  })

  it('update-downloaded → update:status { status: "downloaded" }', () => {
    const { emitter } = makeEmitter()
    const { send, logs } = makeSender()
    registerUpdaterEvents(emitter as never, send)
    emitter.emit('update-downloaded')
    expect(logs).toEqual([{ channel: 'update:status', payload: { status: 'downloaded' } }])
  })

  it('error → update:status { status: "error", message }', () => {
    const { emitter } = makeEmitter()
    const { send, logs } = makeSender()
    registerUpdaterEvents(emitter as never, send)
    emitter.emit('error', { message: 'network timeout' })
    expect(logs).toEqual([
      { channel: 'update:status', payload: { status: 'error', message: 'network timeout' } },
    ])
  })

  it('download-progress → update:download-progress { percent }（取整）', () => {
    const { emitter } = makeEmitter()
    const { send, logs } = makeSender()
    registerUpdaterEvents(emitter as never, send)
    emitter.emit('download-progress', { percent: 37.6, bytesPerSecond: 1024 })
    expect(logs).toEqual([{ channel: 'update:download-progress', payload: { percent: 38 } }])
  })

  it('percent 为 0 和 100 时边界正确', () => {
    const { emitter } = makeEmitter()
    const { send, logs } = makeSender()
    registerUpdaterEvents(emitter as never, send)
    emitter.emit('download-progress', { percent: 0, bytesPerSecond: 0 })
    emitter.emit('download-progress', { percent: 100, bytesPerSecond: 5 * 1024 * 1024 })
    expect(logs.map((l) => l.payload)).toEqual([{ percent: 0 }, { percent: 100 }])
  })
})
