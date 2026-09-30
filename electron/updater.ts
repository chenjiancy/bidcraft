/**
 * 自动更新框架初始化：装配配置、分发事件、触发检查。
 *
 * 主进程调用入口，依赖 electron / electron-updater。
 * 配置与事件逻辑已抽离至 update-config.ts / update-dispatch.ts，可独立单测。
 */
import { BrowserWindow } from 'electron'
import { autoUpdater } from 'electron-updater'
import { UPDATE_CONFIG, UPDATE_STRATEGY } from './lib/update-config'
import { registerUpdaterEvents } from './lib/update-dispatch'

/**
 * 初始化自动更新：配置 feed URL、设置策略、注册事件、启动检查。
 *
 * @param win - 主窗口引用，用于向渲染进程发送 IPC 事件
 */
export function initUpdater(win: BrowserWindow): void {
  autoUpdater.setFeedURL(UPDATE_CONFIG)

  autoUpdater.autoDownload = UPDATE_STRATEGY.autoDownload
  autoUpdater.autoInstallOnAppQuit = UPDATE_STRATEGY.autoInstallOnAppQuit

  const send = (channel: string, payload?: unknown): void => {
    win.webContents.send(channel, payload)
  }

  registerUpdaterEvents(autoUpdater, send)

  // 启动时自动检查更新（静默后台下载，退出时自动安装）
  autoUpdater.checkForUpdates()
}
