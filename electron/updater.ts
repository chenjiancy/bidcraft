import { autoUpdater } from 'electron-updater'

/**
 * 自动更新框架入口（Task 1 仅落地依赖与最小配置）。
 * 发布源：GitHub Releases（owner/repo 见下）。
 * 检查更新/下载/安装逻辑在阶段 1.0 末或发布前完善（architecture.md 11.4）。
 */
export function initUpdater(): void {
  autoUpdater.setFeedURL({
    provider: 'github',
    owner: 'chenjiancy',
    repo: 'bidcraft',
  })
  autoUpdater.autoDownload = false
  autoUpdater.autoInstallOnAppQuit = true
}
