import { contextBridge, ipcRenderer } from 'electron'

const api = {
  app: {
    getVersion: (): Promise<string> => ipcRenderer.invoke('app:getVersion'),
    getUserDataPath: (): Promise<string> => ipcRenderer.invoke('app:getPath', 'userData'),
    quitAndInstall: (): Promise<void> => ipcRenderer.invoke('app:quitAndInstall'),
  },
  win: {
    /** 查询窗口外观能力：是否启用系统磨玻璃材质、标题栏高度 */
    getChrome: (): Promise<{ material: 'acrylic' | 'solid'; titlebarHeight: number }> =>
      ipcRenderer.invoke('window:getChrome'),
    /** 同步原生窗口控件符号色（跟随明暗主题） */
    setTitleBarOverlay: (symbolColor: string): Promise<void> =>
      ipcRenderer.invoke('window:setTitleBarOverlay', symbolColor),
  },
  update: {
    /** 主动触发版本检查，结果通过 onStatus / onDownloadProgress 回调接收 */
    checkForUpdates: (): Promise<{ ok: boolean }> => ipcRenderer.invoke('update:check'),
    /**
     * 监听更新状态事件：{ status: 'checking'|'available'|'not_available'|'downloaded'|'error', message? }
     * 返回清理函数，在组件卸载时调用。
     */
    onStatus: (cb: (payload: unknown) => void): (() => void) => {
      const listener = (_event: Electron.IpcRendererEvent, payload: unknown): void => cb(payload)
      ipcRenderer.on('update:status', listener as Parameters<typeof ipcRenderer.on>[1])
      return () => ipcRenderer.removeListener('update:status', listener)
    },
    /**
     * 监听下载进度：{ percent: number }
     * 返回清理函数，在组件卸载时调用。
     */
    onDownloadProgress: (cb: (payload: { percent: number }) => void): (() => void) => {
      const listener = (_event: Electron.IpcRendererEvent, payload: { percent: number }): void =>
        cb(payload)
      ipcRenderer.on('update:download-progress', listener as Parameters<typeof ipcRenderer.on>[1])
      return () => ipcRenderer.removeListener('update:download-progress', listener)
    },
  },
  sidecar: {
    /** 查询 Python 健康状态（含 Main 侧状态机与实际 /health 响应） */
    health: (): Promise<unknown> => ipcRenderer.invoke('sidecar:health'),
    /**
     * 统一转发到 sidecar（带本地令牌）。
     * 未指定 method 时：有 payload 走 POST，无 payload 走 GET。
     * 指定 method 时按 method 走（支持 PUT/PATCH/DELETE）。
     */
    call: (route: string, payload?: unknown, method?: string): Promise<unknown> =>
      ipcRenderer.invoke('sidecar:call', route, payload, method),
    /**
     * 订阅 SSE 进度流。
     * @param onProgress 每条事件（含终态）回调
     * @returns 终态事件
     */
    stream: async (
      route: string,
      payload: unknown,
      onProgress: (event: unknown) => void,
    ): Promise<unknown> => {
      const requestId = `${Date.now()}-${Math.random().toString(36).slice(2)}`
      const channel = 'sidecar:stream:event'
      const listener = (_event: unknown, id: string, event: unknown): void => {
        if (id === requestId) onProgress(event)
      }
      ipcRenderer.on(channel, listener)
      try {
        return await ipcRenderer.invoke('sidecar:stream', requestId, route, payload)
      } finally {
        ipcRenderer.removeListener(channel, listener)
      }
    },
    /** 请求取消异步任务 */
    cancelTask: (taskId: string): Promise<unknown> => ipcRenderer.invoke('task:cancel', taskId),
  },
  dialog: {
    /** 打开本机招标文件选择对话框，返回选中文件（绝对路径，供同机 sidecar 入库） */
    openBidFiles: (): Promise<Array<{ name: string; path: string }>> =>
      ipcRenderer.invoke('dialog:openBidFiles'),
    /** Task 15：选择素材文件（PDF/Word/图片） */
    openMaterialFiles: (): Promise<Array<{ name: string; path: string }>> =>
      ipcRenderer.invoke('dialog:openMaterialFiles'),
  },
  shell: {
    /** Task 13：用系统默认应用打开 docx 文件（路径校验在 Main 侧） */
    openDocxFile: (
      enterpriseId: string,
      projectId: string,
      sourceStem: string,
      file: string,
    ): Promise<{ opened: boolean; path: string }> =>
      ipcRenderer.invoke('shell:openDocxFile', enterpriseId, projectId, sourceStem, file),
  },
  shell: {
    /** Task 13：用系统默认应用打开 docx 文件（路径校验在 Main 侧） */
    openDocxFile: (
      enterpriseId: string,
      projectId: string,
      sourceStem: string,
      file: string,
    ): Promise<{ opened: boolean; path: string }> =>
      ipcRenderer.invoke('shell:openDocxFile', enterpriseId, projectId, sourceStem, file),
  },
  cred: {
    /** 保存 API Key（DPAPI 加密存储） */
    setApiKey: (apiKey: string): Promise<{ success: boolean }> =>
      ipcRenderer.invoke('cred:setApiKey', apiKey),
    /** 读取 API Key（DPAPI 解密） */
    getApiKey: (): Promise<string | null> => ipcRenderer.invoke('cred:getApiKey'),
    /** 检查是否已设置 API Key */
    hasApiKey: (): Promise<boolean> => ipcRenderer.invoke('cred:hasApiKey'),
    /** 清除 API Key */
    clearApiKey: (): Promise<{ success: boolean }> => ipcRenderer.invoke('cred:clearApiKey'),
  },
}

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('bid', api)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-expect-error 非 contextIsolation 兜底（正常配置不会走到）
  window.bid = api
}

export type BidAPI = typeof api
