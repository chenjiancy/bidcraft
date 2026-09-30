/**
 * 自动更新配置：声明式定义 feed URL 与更新策略常量。
 *
 * 从 initUpdater 中抽离，使配置本身可独立断言，
 * 且不依赖 electron / electron-updater 模块。
 */
export interface UpdateFeedConfig {
  provider: 'github'
  owner: string
  repo: string
}

export const UPDATE_CONFIG: Readonly<UpdateFeedConfig> = {
  provider: 'github',
  owner: 'chenjiancy',
  repo: 'bidcraft',
} as const

/** 静默后台下载 + 退出时自动安装，两个策略均为 true */
export const UPDATE_STRATEGY = {
  autoDownload: true,
  autoInstallOnAppQuit: true,
} as const
