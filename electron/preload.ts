import { contextBridge, ipcRenderer } from 'electron'

const api = {
  app: {
    getVersion: (): Promise<string> => ipcRenderer.invoke('app:getVersion'),
    getUserDataPath: (): Promise<string> => ipcRenderer.invoke('app:getPath', 'userData'),
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
