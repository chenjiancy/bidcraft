import '@testing-library/jest-dom/vitest'

import type { BidAPI } from '../types/global'

// jsdom 未实现 matchMedia；antd 响应式组件依赖它，提供最小 mock
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})

// Electron preload API mock（jsdom 环境无 Electron；sidecar.call 按路由返回默认值）
window.bid = {
  app: {
    getVersion: () => Promise.resolve('0.0.0'),
    getUserDataPath: () => Promise.resolve(''),
  },
  sidecar: {
    health: () => Promise.resolve({ status: 'healthy' }),
    call: (route: string) => {
      // 模型配置路由返回合理默认值
      if (route.includes('/model-config/external-confirmed'))
        return Promise.resolve({ confirmed: false })
      if (route.includes('/model-config'))
        return Promise.resolve({ provider: null, base_url: null, model: null })
      if (route.endsWith('/parse/engine'))
        return Promise.resolve({
          available: true,
          cuda_available: true,
          libreoffice_available: true,
        })
      if (route.endsWith('/parse/status'))
        return Promise.resolve({
          parse_status: 'INIT',
          running: false,
          sources: {},
          checkpoint: null,
          chapters: null,
          dedupe: null,
        })
      return Promise.resolve([])
    },
    stream: () => Promise.resolve({ stage: 'completed', percent: 100, message: '' }),
    cancelTask: () => Promise.resolve({}),
  },
  dialog: {
    openBidFiles: () => Promise.resolve([]),
  },
  cred: {
    setApiKey: () => Promise.resolve({ success: true }),
    getApiKey: () => Promise.resolve(null),
    hasApiKey: () => Promise.resolve(false),
    clearApiKey: () => Promise.resolve({ success: true }),
  },
} as unknown as BidAPI
