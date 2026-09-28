import { execFileSync } from 'node:child_process'
import { join } from 'node:path'
import { _electron as electron, expect, test } from '@playwright/test'

test('sidecar 自动拉起、健康检查、SSE 事件流与取消', async () => {
  const app = await electron.launch({ args: [join(__dirname, '..')] })
  const page = await app.firstWindow()

  // TR-3.1：应用启动自动拉起 sidecar，/health 返回 200（轮询等待就绪）
  const health = await page.evaluate(async () => {
    let result: Awaited<ReturnType<Window['bid']['sidecar']['health']>> | null = null
    for (let i = 0; i < 40; i++) {
      result = await window.bid.sidecar.health()
      if (result.status === 'healthy') return result
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
    throw new Error(`sidecar 未在 20s 内就绪：${JSON.stringify(result)}`)
  })
  expect(health.status).toBe('healthy')
  expect(health.port).toEqual(expect.any(Number))
  expect(health.health).toEqual({ status: 'ok' })

  // TR-3.3：该端口监听地址仅为 127.0.0.1
  const addresses = execFileSync(
    'powershell',
    [
      '-NoProfile',
      '-Command',
      `(Get-NetTCPConnection -LocalPort ${health.port} -State Listen).LocalAddress`,
    ],
    { encoding: 'utf8' },
  )
    .trim()
    .split(/\r?\n/)
  expect(addresses).toEqual(['127.0.0.1'])

  // TR-3.2：Renderer 经 IPC → sidecar 收到完整 SSE 事件序列
  const normal = await page.evaluate(async () => {
    const collected: unknown[] = []
    const finalEvent = await window.bid.sidecar.stream('/api/v1/test/stream', {}, (event) =>
      collected.push(event),
    )
    return {
      stages: (collected as Array<{ stage: string }>).map((e) => e.stage),
      finalEvent,
    }
  })
  expect(normal.stages).toEqual(['queued', 'progress', 'progress', 'completed'])
  expect(normal.finalEvent.stage).toBe('completed')

  // 取消：首个事件后立即请求取消，终态必须为 cancelled
  const cancelled = await page.evaluate(async () => {
    const collected: Array<{ extra: { task_id: string } }> = []
    const promise = window.bid.sidecar.stream('/api/v1/test/stream', {}, (event) => {
      collected.push(event as { extra: { task_id: string } })
      if (collected.length === 1) {
        void window.bid.sidecar.cancelTask(collected[0].extra.task_id)
      }
    })
    return promise
  })
  expect(cancelled.stage).toBe('cancelled')

  // 非法路由在 Main 侧被拦截
  await expect(
    page.evaluate(() => window.bid.sidecar.call('http://evil.example.com/x')),
  ).rejects.toThrow(/非法路由/)

  // 崩溃检测：外部强杀 sidecar 进程树，Main 状态机应标记 crashed
  const owningProcess = execFileSync(
    'powershell',
    [
      '-NoProfile',
      '-Command',
      `(Get-NetTCPConnection -LocalPort ${health.port} -State Listen).OwningProcess`,
    ],
    { encoding: 'utf8' },
  ).trim()
  execFileSync('taskkill', ['/PID', owningProcess, '/T', '/F'])

  const crashed = await page.evaluate(async () => {
    let result: Awaited<ReturnType<Window['bid']['sidecar']['health']>> | null = null
    for (let i = 0; i < 20; i++) {
      result = await window.bid.sidecar.health()
      if (result.status === 'crashed') return result
      await new Promise((resolve) => setTimeout(resolve, 300))
    }
    throw new Error(`未检测到 crashed 状态：${JSON.stringify(result)}`)
  })
  expect(crashed.status).toBe('crashed')

  await app.close()

  // TR-3.1：应用退出后 sidecar 进程消失（按命令行精确识别 sidecar python）
  await new Promise((resolve) => setTimeout(resolve, 2000))
  const leftover = execFileSync(
    'powershell',
    [
      '-NoProfile',
      '-Command',
      '(Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'" | ' +
        "Where-Object { $_.CommandLine -match 'app\\.main:app' } | Measure-Object).Count",
    ],
    { encoding: 'utf8' },
  ).trim()
  expect(leftover).toBe('0')
})
