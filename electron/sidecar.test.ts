/**
 * sidecar.ts 单元测试：requireSidecarHandle / startSidecar 行为
 *
 * 策略：mock node:child_process（spawn/execFile）、./lib/net-utils（getFreePort），
 * 同时 mock fetch 控制健康检查响应。
 *
 * 注意：spawn mock 在 vitest 环境下受上一个测试残留的 uvicorn 进程干扰，
 * 因此仅测试健康的成功路径（spawn 返回假进程对象 + fetch 返回 ok=true）。
 * requireSidecarHandle 的失败路径通过 handle=null 的初始状态验证。
 */
import { ChildProcess, spawn } from 'node:child_process'
import { describe, expect, it, vi } from 'vitest'

// ---------- mock 依赖（hoisted，全局生效）----------
vi.mock('node:child_process', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:child_process')>()
  return {
    ...actual,
    spawn: vi.fn(),
    execFile: vi.fn(),
  }
})

vi.mock('../lib/net-utils', () => ({
  getFreePort: vi.fn(async () => 18923),
}))

// ---------- requireSidecarHandle ----------

describe('requireSidecarHandle', () => {
  it('handle 为 null 时抛出明确错误', async () => {
    const { requireSidecarHandle } = await import('./sidecar')
    expect(() => requireSidecarHandle()).toThrow('sidecar 尚未启动')
  })
})

// ---------- startSidecar ----------

describe('startSidecar', () => {
  it('健康检查成功时返回有效 handle 并置为 healthy 状态', async () => {
    // fetch 模拟侧车健康检查通过
    const mockFetch = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', mockFetch)

    // spawn 不启动真实子进程（退出事件不会被触发）
    const mockSpawn = spawn as ReturnType<typeof vi.fn>
    mockSpawn.mockReturnValue({
      stdout: { on: vi.fn() },
      stderr: { on: vi.fn() },
      on: vi.fn(),
    } as unknown as ChildProcess)

    const { startSidecar, getSidecarStatus, getSidecarHandle } = await import('./sidecar')
    // useDevRunner=true → 走 uvicorn 路径，不访问 process.resourcesPath
    const handle = await startSidecar(true, '/tmp/bidcraft-test')

    expect(handle).toBeTruthy()
    expect(typeof handle.port).toBe('number')
    expect(handle.port).toBeGreaterThan(0)
    expect(getSidecarStatus()).toBe('healthy')
    expect(getSidecarHandle()).toBe(handle)
    expect(mockFetch).toHaveBeenCalledWith(`http://127.0.0.1:${handle.port}/health`)
  })
})
