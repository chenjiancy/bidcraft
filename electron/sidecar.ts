import { execFile, type ChildProcess, spawn } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { join } from 'node:path'
import { getFreePort } from './lib/net-utils'

export type SidecarStatus = 'starting' | 'healthy' | 'crashed' | 'stopped'

export interface SidecarHandle {
  port: number
  token: string
}

const HEALTH_TIMEOUT_MS = 30_000
const HEALTH_INTERVAL_MS = 300

let child: ChildProcess | null = null
let handle: SidecarHandle | null = null
let status: SidecarStatus = 'stopped'
let stopping = false

export function getSidecarStatus(): SidecarStatus {
  return status
}

export function getSidecarHandle(): SidecarHandle | null {
  return handle
}

/** 取当前连接信息，未就绪时直接抛错（供 IPC 处理器使用） */
export function requireSidecarHandle(): SidecarHandle {
  if (!handle) throw new Error('sidecar 尚未启动')
  return handle
}

async function waitForHealth(port: number): Promise<void> {
  const deadline = Date.now() + HEALTH_TIMEOUT_MS
  let lastError: unknown = null

  while (Date.now() < deadline) {
    if (status !== 'starting') {
      throw new Error('sidecar 启动期间状态异常终止')
    }
    try {
      const resp = await fetch(`http://127.0.0.1:${port}/health`)
      if (resp.ok) {
        status = 'healthy'
        return
      }
    } catch (err) {
      lastError = err
    }
    await new Promise((resolve) => setTimeout(resolve, HEALTH_INTERVAL_MS))
  }

  throw new Error(`sidecar 健康检查超时：${String(lastError)}`)
}

/**
 * 拉起 Python sidecar（随机端口 + 本地令牌）。
 * - useDevRunner=true：直接运行 .venv 内的 uvicorn（开发 / 未打包运行，
 *   不经 shell/cmd，保证 child.pid 就是真实进程、进程树可整树结束）；
 * - false：PyInstaller exe（打包后，随 1.2 打包链路落地）。
 */
export async function startSidecar(
  useDevRunner: boolean,
  dataRoot: string,
): Promise<SidecarHandle> {
  stopping = false
  status = 'starting'

  const port = await getFreePort()
  const token = randomBytes(24).toString('hex')
  handle = { port, token }

  const env = {
    ...process.env,
    BIDCRAFT_DATA_ROOT: dataRoot,
    BIDCRAFT_SIDECAR_TOKEN: token,
    PYTHONUNBUFFERED: '1',
  }

  if (useDevRunner) {
    const sidecarDir = join(process.cwd(), 'sidecar')
    const runner =
      process.platform === 'win32'
        ? join(sidecarDir, '.venv', 'Scripts', 'uvicorn.exe')
        : join(sidecarDir, '.venv', 'bin', 'uvicorn')
    child = spawn(runner, ['app.main:app', '--host', '127.0.0.1', '--port', String(port)], {
      cwd: sidecarDir,
      env,
    })
  } else {
    const exe = join(process.resourcesPath, 'sidecar', 'bidcraft-sidecar.exe')
    child = spawn(exe, ['--data-root', dataRoot], { env })
  }

  child.stdout?.on('data', (d: Buffer) => console.log(`[sidecar] ${String(d).trimEnd()}`))
  child.stderr?.on('data', (d: Buffer) => console.warn(`[sidecar] ${String(d).trimEnd()}`))
  child.on('error', (err) => console.error('[sidecar] 进程错误：', err))
  child.on('exit', (code) => {
    console.log(`[sidecar] 退出 code=${code}`)
    // 非主动停止即判定崩溃（NFR：不静默）
    if (!stopping) status = 'crashed'
  })

  await waitForHealth(port).catch(async (err) => {
    // M6 修复：健康检查超时/失败时终止侧车进程，避免僵尸进程
    status = 'crashed'
    const c = child
    if (c?.pid) {
      if (process.platform === 'win32') {
        await new Promise<void>((resolve) => {
          execFile('taskkill', ['/pid', String(c.pid), '/T', '/F'], () => resolve())
        })
      } else {
        c.kill()
      }
    }
    child = null
    handle = null
    throw err
  })
  return handle
}

/** 优雅停止 sidecar；等待进程树真正结束后再返回 */
export async function stopSidecar(): Promise<void> {
  stopping = true
  status = 'stopped'

  const current = child
  child = null
  handle = null

  if (!current?.pid) return

  if (process.platform === 'win32') {
    // /T 结束 uvicorn→python 进程树；忽略"进程已不存在"类错误
    await new Promise<void>((resolve) => {
      execFile('taskkill', ['/pid', String(current.pid), '/T', '/F'], () => resolve())
    })
  } else {
    current.kill()
  }
}
