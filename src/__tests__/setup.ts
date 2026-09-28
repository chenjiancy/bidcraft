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

// Electron preload API mock（jsdom 环境无 Electron；sidecar.call 默认返回空数组）
window.bid = {
  app: {
    getVersion: () => Promise.resolve('0.0.0'),
    getUserDataPath: () => Promise.resolve(''),
  },
  sidecar: {
    health: () => Promise.resolve({ status: 'healthy' }),
    call: () => Promise.resolve([]),
    stream: () => Promise.resolve({ stage: 'completed', percent: 100, message: '' }),
    cancelTask: () => Promise.resolve({}),
  },
} as unknown as BidAPI
