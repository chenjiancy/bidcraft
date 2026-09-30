/**
 * Renderer 全局类型声明。
 * 注意：与 electron/preload.ts 中 BidAPI 保持同步。
 */

export interface ProgressEvent {
  stage: string
  percent: number
  message: string
  extra?: Record<string, unknown>
}

export interface SidecarHealthResult {
  status: 'starting' | 'healthy' | 'crashed' | 'stopped'
  port?: number
  health?: { status: string }
  error?: string
}

export interface UpdateStatusEvent {
  status: 'checking' | 'available' | 'not_available' | 'downloaded' | 'error'
  message?: string
}

export interface UpdateDownloadProgress {
  percent: number
}

export interface BidAPI {
  app: {
    getVersion: () => Promise<string>
    getUserDataPath: () => Promise<string>
    quitAndInstall: () => Promise<void>
  }
  win: {
    getChrome: () => Promise<{ material: 'acrylic' | 'solid'; titlebarHeight: number }>
    setTitleBarOverlay: (symbolColor: string) => Promise<void>
  }
  update: {
    checkForUpdates: () => Promise<{ ok: boolean }>
    onStatus: (cb: (payload: UpdateStatusEvent) => void) => () => void
    onDownloadProgress: (cb: (payload: UpdateDownloadProgress) => void) => () => void
  }
  sidecar: {
    health: () => Promise<SidecarHealthResult>
    call: (route: string, payload?: unknown, method?: string) => Promise<unknown>
    stream: (
      route: string,
      payload: unknown,
      onProgress: (event: ProgressEvent) => void,
    ) => Promise<ProgressEvent>
    cancelTask: (taskId: string) => Promise<unknown>
  }
  dialog: {
    openBidFiles: () => Promise<Array<{ name: string; path: string }>>
    openMaterialFiles: () => Promise<Array<{ name: string; path: string }>>
  }
  shell: {
    openDocxFile: (
      enterpriseId: string,
      projectId: string,
      sourceStem: string,
      file: string,
    ) => Promise<{ opened: boolean; path: string }>
  }
  shell: {
    openDocxFile: (
      enterpriseId: string,
      projectId: string,
      sourceStem: string,
      file: string,
    ) => Promise<{ opened: boolean; path: string }>
  }
  cred: {
    setApiKey: (apiKey: string) => Promise<{ success: boolean }>
    getApiKey: () => Promise<string | null>
    hasApiKey: () => Promise<boolean>
    clearApiKey: () => Promise<{ success: boolean }>
  }
}

declare global {
  interface Window {
    bid: BidAPI
  }
}
