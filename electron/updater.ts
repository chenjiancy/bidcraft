import { BrowserWindow } from 'electron'
import { autoUpdater } from 'electron-updater'

/**
 * 自动更新框架初始化。
 * 策略：静默后台下载 + app 退出时自动安装（无需用户干预）。
 * 事件通过 IPC 转发到渲染进程，供前端显示更新状态。
 */
export function initUpdater(win: BrowserWindow): void {
  autoUpdater.setFeedURL({
    provider: 'github',
    owner: 'chenjiancy',
    repo: 'bidcraft',
  })

  // 静默后台下载；安装在应用退出时自动进行
  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true

  const send = (channel: string, payload?: unknown): void => {
    win.webContents.send(channel, payload)
  }

  autoUpdater.on('checking-for-update', () => send('update:status', { status: 'checking' }))

  autoUpdater.on('update-available', () => send('update:status', { status: 'available' }))

  autoUpdater.on('update-not-available', () => send('update:status', { status: 'not_available' }))

  autoUpdater.on('download-progress', (progress: { percent: number; bytesPerSecond: number }) =>
    send('update:download-progress', { percent: Math.round(progress.percent) }),
  )

  autoUpdater.on('update-downloaded', () => send('update:status', { status: 'downloaded' }))

  autoUpdater.on('error', (err: { message: string }) =>
    send('update:status', { status: 'error', message: err.message }),
  )
}
