/**
 * Renderer 全局类型声明。
 * 注意：与 electron/preload.ts 中 BidAPI 保持同步。
 */
export interface BidAPI {
  app: {
    getVersion: () => Promise<string>
    getUserDataPath: () => Promise<string>
  }
}

declare global {
  interface Window {
    bid: BidAPI
  }
}
