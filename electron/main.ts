import { app, BrowserWindow, ipcMain, shell } from 'electron'
import { join } from 'node:path'
import { startSidecar, stopSidecar } from './sidecar'
import { initUpdater } from './updater'

// dev/prod 环境检测（architecture.md 10.1）：
// electron-vite 在开发模式下注入 ELECTRON_RENDERER_URL，比 NODE_ENV 可靠
const isDev = !!process.env.ELECTRON_RENDERER_URL

// 必须在 app.whenReady() 之前设置，使 userData 分流到不同目录
app.setName(isDev ? 'BidCraft-dev' : 'BidCraftApp')

function createWindow(): void {
  const mainWindow = new BrowserWindow({
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

  mainWindow.on('ready-to-show', () => mainWindow.show())

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

app.whenReady().then(() => {
  console.log(`[main] env=${isDev ? 'dev' : 'prod'} userData=${app.getPath('userData')}`)

  ipcMain.handle('app:getVersion', () => app.getVersion())
  ipcMain.handle('app:getPath', (_event, name: string) => {
    // 白名单：仅允许查询 userData，杜绝任意路径探测
    if (name !== 'userData') throw new Error(`未授权的路径: ${name}`)
    return app.getPath('userData')
  })

  // sidecar 自动拉起（Task 1 最小版：固定端口；随机端口/令牌/健康检查/崩溃检测在 Task 3）
  startSidecar(isDev, app.getPath('userData')).catch((err: unknown) =>
    console.error('[main] sidecar 启动失败：', err),
  )

  // 自动更新框架入口（仅依赖与配置；检查更新/安装逻辑发布前完善）
  initUpdater()

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  stopSidecar()
})
