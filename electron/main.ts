import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import { basename, join, resolve, sep } from 'node:path'
import { isTerminalStage, parseSSE, type ProgressEvent } from './lib/sse'
import {
  getSidecarHandle,
  getSidecarStatus,
  requireSidecarHandle,
  startSidecar,
  stopSidecar,
} from './sidecar'
import { initUpdater } from './updater'
import { autoUpdater } from 'electron-updater'
import { registerCredIpc } from './cred'

// dev/prod 环境检测（architecture.md 10.1）：
// electron-vite 在开发模式下注入 ELECTRON_RENDERER_URL，比 NODE_ENV 可靠
const isDev = !!process.env.ELECTRON_RENDERER_URL

// 未打包运行（含 electron-vite dev 与 Playwright 直跑）走 uv；打包后走 exe
const useDevRunner = !app.isPackaged

// 必须在 app.whenReady() 之前设置，使 userData 分流到不同目录
app.setName(isDev ? 'BidCraft-dev' : 'BidCraftApp')

// 主窗口引用（updater 需要向它发送事件）
let mainWindow: BrowserWindow | null = null

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 680,
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/preload.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  mainWindow!.on('ready-to-show', () => mainWindow!.show())

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  if (isDev && process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

/** 仅允许 /api/v1 下的常规路径（含可选 query string），杜绝 SSRF/任意路径探测 */
const ALLOWED_ROUTE = /^\/api\/v1\/[a-z0-9_]+(?:\/[a-z0-9_]+)*(?:\?[^/]*)?$/i

/** 仅允许标准 HTTP 方法，杜绝任意动词 */
const ALLOWED_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

function registerSidecarIpc(): void {
  ipcMain.handle('sidecar:health', async () => {
    const h = getSidecarHandle()
    if (!h) return { status: getSidecarStatus() }
    try {
      const resp = await fetch(`http://127.0.0.1:${h.port}/health`, {
        signal: AbortSignal.timeout(2000),
      })
      return { status: getSidecarStatus(), port: h.port, health: await resp.json() }
    } catch (err) {
      return { status: getSidecarStatus(), port: h.port, error: String(err) }
    }
  })

  ipcMain.handle(
    'sidecar:call',
    async (_event, route: string, payload?: unknown, method?: string): Promise<unknown> => {
      const h = requireSidecarHandle()
      if (!ALLOWED_ROUTE.test(route)) throw new Error(`非法路由: ${route}`)

      const resolvedMethod = method ?? (payload !== undefined ? 'POST' : 'GET')
      const upper = resolvedMethod.toUpperCase()
      if (!ALLOWED_METHODS.includes(upper as (typeof ALLOWED_METHODS)[number])) {
        throw new Error(`非法方法: ${method}`)
      }

      const init: RequestInit = { method: upper, headers: authHeaders(h.token) }
      if (payload !== undefined) {
        init.headers = {
          ...(init.headers as Record<string, string>),
          'Content-Type': 'application/json',
        }
        init.body = JSON.stringify(payload)
      }

      const resp = await fetch(`http://127.0.0.1:${h.port}${route}`, init)
      const text = await resp.text()
      if (!resp.ok) throw new Error(`sidecar 调用失败 HTTP ${resp.status}: ${text}`)
      return text ? JSON.parse(text) : null
    },
  )

  ipcMain.handle(
    'sidecar:stream',
    async (event, requestId: string, route: string, payload?: unknown): Promise<ProgressEvent> => {
      const h = requireSidecarHandle()
      if (!ALLOWED_ROUTE.test(route)) throw new Error(`非法路由: ${route}`)

      const send = (progress: ProgressEvent): void => {
        event.sender.send('sidecar:stream:event', requestId, progress)
      }

      try {
        const resp = await fetch(`http://127.0.0.1:${h.port}${route}`, {
          method: 'POST',
          headers: {
            ...authHeaders(h.token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload ?? {}),
        })
        if (!resp.ok) {
          throw new Error(`sidecar 流建立失败 HTTP ${resp.status}: ${await resp.text()}`)
        }

        // 先把任务 ID 作为元事件下发，供渲染端调用取消（body 首条 SSE 之前）
        const taskId = resp.headers.get('x-task-id')
        if (taskId) send({ stage: 'meta', percent: 0, message: '', extra: { taskId } })

        let last: ProgressEvent | null = null
        for await (const progress of parseSSE(resp)) {
          last = progress
          send(progress)
          if (isTerminalStage(progress.stage)) break
        }
        if (!last) throw new Error('sidecar 流未产生任何事件')
        return last
      } catch (err) {
        const failed: ProgressEvent = {
          stage: 'failed',
          percent: 0,
          message: err instanceof Error ? err.message : String(err),
        }
        send(failed)
        return failed
      }
    },
  )

  ipcMain.handle('task:cancel', async (_event, taskId: string) => {
    const h = requireSidecarHandle()
    if (!/^[a-z0-9-]+$/i.test(taskId)) throw new Error(`非法任务 ID: ${taskId}`)

    const resp = await fetch(`http://127.0.0.1:${h.port}/api/v1/tasks/${taskId}/cancel`, {
      method: 'POST',
      headers: authHeaders(h.token),
    })
    const text = await resp.text()
    if (!resp.ok) throw new Error(`取消失败 HTTP ${resp.status}: ${text}`)
    return JSON.parse(text)
  })
}

app.whenReady().then(() => {
  console.log(`[main] env=${isDev ? 'dev' : 'prod'} userData=${app.getPath('userData')}`)

  ipcMain.handle('app:getVersion', () => app.getVersion())
  ipcMain.handle('app:getPath', (_event, name: string) => {
    // 白名单：仅允许查询 userData，杜绝任意路径探测
    if (name !== 'userData') throw new Error(`未授权的路径: ${name}`)
    return app.getPath('userData')
  })

  // 本机招标文件选择：sidecar 与 Electron 同机，直接回传绝对路径入库
  ipcMain.handle('dialog:openBidFiles', async () => {
    const win = BrowserWindow.getFocusedWindow() ?? BrowserWindow.getAllWindows()[0]
    const result = await dialog.showOpenDialog(win, {
      title: '选择招标文件',
      properties: ['openFile', 'multiSelections'],
      filters: [{ name: '招标文件 (PDF/Word)', extensions: ['pdf', 'doc', 'docx'] }],
    })
    if (result.canceled) return []
    return result.filePaths.map((path) => ({ name: basename(path), path }))
  })

  // 素材文件选择（Task 15）：支持 PDF/Word/图片
  ipcMain.handle('dialog:openMaterialFiles', async () => {
    const win = BrowserWindow.getFocusedWindow() ?? BrowserWindow.getAllWindows()[0]
    const result = await dialog.showOpenDialog(win, {
      title: '选择素材文件',
      properties: ['openFile', 'multiSelections'],
      filters: [
        {
          name: '素材文件 (PDF/Word/图片)',
          extensions: ['pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg', 'bmp', 'tiff'],
        },
      ],
    })
    if (result.canceled) return []
    return result.filePaths.map((path) => ({ name: basename(path), path }))
  })

  registerSidecarIpc()
  registerCredIpc()

  // Task 13：用系统默认应用打开 docx 文件（路径穿越防护）
  ipcMain.handle(
    'shell:openDocxFile',
    async (_event, enterpriseId: string, projectId: string, sourceStem: string, file: string) => {
      const base = join(
        app.getPath('userData'),
        'enterprises',
        enterpriseId,
        'projects',
        projectId,
        'parse',
        'docx',
      )
      // safe_filename 等价：清洗非法字符（与 sidecar paths.safe_filename 同构）
      const safeStem = sourceStem.replace(/[<>:"/\\|?*]/g, '_').slice(0, 180)
      const safeFile = file.replace(/[<>:"/\\|?*]/g, '_').slice(0, 180)
      const absPath = resolve(base, safeStem, safeFile)
      // 路径穿越防护：resolve 后必须在 docx 目录内
      const expectedPrefix = resolve(base) + sep
      if (!absPath.startsWith(expectedPrefix)) {
        throw new Error(`路径越权: ${file}`)
      }
      const result = await shell.openPath(absPath)
      return { opened: !result, path: absPath }
    },
  )

  // sidecar 自动拉起（随机端口 + 本地令牌 + 健康检查 + 崩溃检测）
  startSidecar(useDevRunner, app.getPath('userData')).catch((err: unknown) =>
    console.error('[main] sidecar 启动失败：', err),
  )

  // 自动更新：静默后台下载 + app 退出时自动安装
  if (mainWindow) initUpdater(mainWindow)
  // 允许前端主动触发版本检查
  ipcMain.handle('update:check', () => {
    autoUpdater.checkForUpdates()
    return { ok: true }
  })

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

// 退出前先优雅结束 sidecar，并等待进程树真正消失再允许退出
let quitInProgress = false
app.on('before-quit', (event) => {
  if (quitInProgress) return
  event.preventDefault()
  quitInProgress = true
  void stopSidecar().finally(() => app.quit())
})
