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
import { join } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// ---------- mock 依赖（hoisted，全局生效）----------
// node 内置模块经 CJS interop：factory 需同时提供命名导出与 default，
// 且两者必须指向同一批 vi.fn（default 不能 spread actual，否则 sidecar.ts
// 经 CJS default 导入时仍会拿到原生 spawn）。
const cpMock = vi.hoisted(() => ({
  spawn: vi.fn(),
  execFile: vi.fn(),
}))

vi.mock('node:child_process', () => ({
  spawn: cpMock.spawn,
  execFile: cpMock.execFile,
  default: cpMock,
}))

// 注意：mock 路径相对测试文件本身解析，本文件在 electron/ 下，
// sidecar.ts 以 './lib/net-utils' 引入，故这里同样是 './lib/net-utils'
// （写成 '../lib/...' 会解析到项目根的不存在目录，vitest 静默不匹配）。
vi.mock('./lib/net-utils', () => ({
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
  beforeEach(() => {
    ;(spawn as ReturnType<typeof vi.fn>).mockClear()
  })

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

  it('开发模式不注入 BIDCRAFT_RESOURCES_PATH', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', mockFetch)

    const mockSpawn = spawn as ReturnType<typeof vi.fn>
    mockSpawn.mockReturnValue({
      stdout: { on: vi.fn() },
      stderr: { on: vi.fn() },
      on: vi.fn(),
    } as unknown as ChildProcess)

    const { startSidecar } = await import('./sidecar')
    await startSidecar(true, '/tmp/bidcraft-dev')

    expect(mockSpawn).toHaveBeenCalledTimes(1)
    const spawnOptions = mockSpawn.mock.calls[0]?.[2] as { env: NodeJS.ProcessEnv }
    expect(spawnOptions.env.BIDCRAFT_RESOURCES_PATH).toBeUndefined()
    expect(spawnOptions.env.BIDCRAFT_DATA_ROOT).toBe('/tmp/bidcraft-dev')
    expect(spawnOptions.env.BIDCRAFT_SIDECAR_PORT).toBe('18923')
  })

  it('打包模式从 resourcesPath 拉起 sidecar exe 并注入 BIDCRAFT_RESOURCES_PATH', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', mockFetch)

    const mockSpawn = spawn as ReturnType<typeof vi.fn>
    mockSpawn.mockReturnValue({
      stdout: { on: vi.fn() },
      stderr: { on: vi.fn() },
      on: vi.fn(),
    } as unknown as ChildProcess)

    const { startSidecar } = await import('./sidecar')
    await startSidecar(false, '/tmp/bidcraft-prod', '/tmp/installed/resources')

    expect(mockSpawn).toHaveBeenCalledTimes(1)
    const [exe, args, options] = mockSpawn.mock.calls[0] as [
      string,
      string[],
      { env: NodeJS.ProcessEnv },
    ]
    expect(exe).toBe(join('/tmp/installed/resources', 'sidecar', 'bidcraft-sidecar.exe'))
    expect(args).toEqual(['--data-root', '/tmp/bidcraft-prod'])
    expect(options.env.BIDCRAFT_RESOURCES_PATH).toBe('/tmp/installed/resources')
    expect(options.env.BIDCRAFT_DATA_ROOT).toBe('/tmp/bidcraft-prod')
    expect(options.env.BIDCRAFT_SIDECAR_PORT).toBe('18923')
  })
})
