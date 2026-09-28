import { type ChildProcess, spawn } from 'node:child_process'
import { join } from 'node:path'

// Task 1 使用固定端口；Task 3 改为随机端口 + 本地令牌 + 健康检查
const SIDECAR_PORT = 18765

let child: ChildProcess | null = null

/**
 * 拉起 Python sidecar。
 * - dev：uv run uvicorn（sidecar 目录），经 BIDCRAFT_DATA_ROOT 传数据根；
 * - prod：PyInstaller exe（1.2 随打包链路落地），经 --data-root + 环境变量传数据根。
 */
export async function startSidecar(isDev: boolean, dataRoot: string): Promise<void> {
  if (isDev) {
    const sidecarDir = join(process.cwd(), 'sidecar')
    // Windows 下 uv 为 uv.cmd，需要 shell:true
    child = spawn(`uv run uvicorn app.main:app --host 127.0.0.1 --port ${SIDECAR_PORT}`, {
      cwd: sidecarDir,
      shell: true,
      env: {
        ...process.env,
        BIDCRAFT_DATA_ROOT: dataRoot,
        PYTHONUNBUFFERED: '1',
      },
    })
  } else {
    const exe = join(process.resourcesPath, 'sidecar', 'bidcraft-sidecar.exe')
    child = spawn(exe, ['--data-root', dataRoot], {
      env: { ...process.env, BIDCRAFT_DATA_ROOT: dataRoot },
    })
  }

  child.stdout?.on('data', (d: Buffer) => console.log(`[sidecar] ${String(d).trimEnd()}`))
  child.stderr?.on('data', (d: Buffer) => console.warn(`[sidecar] ${String(d).trimEnd()}`))
  child.on('error', (err) => console.error('[sidecar] 进程错误：', err))
  child.on('exit', (code) => console.log(`[sidecar] 退出 code=${code}`))
}

export function stopSidecar(): void {
  if (!child?.pid) return
  if (process.platform === 'win32') {
    // shell:true 产生 cmd→uv→python 进程树，/T 整树结束，避免端口残留
    spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'])
  } else {
    child.kill()
  }
  child = null
}
