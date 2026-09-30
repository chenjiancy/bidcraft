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

// 解析配置默认项（与后端 app/parse/config.py 目录一致，供 ParsePage 渲染）
const REQUIRED_CONFIG_ITEMS = [
  ['project_overview', '项目概述'],
  ['tech_score', '技术评分要求'],
  ['project_info', '项目信息'],
  ['buyer_info', '甲方信息'],
  ['response_requirements', '响应文件要求'],
  ['agency_info', '代理机构信息'],
  ['business_score', '商务评分要求'],
  ['invalid_bid', '无效标与废标项'],
] as const
const OPTIONAL_CONFIG_ITEMS = [
  ['delivery_service', '交货和服务要求'],
  ['procurement_list', '采购清单'],
  ['bid_milestones', '投标关键节点'],
  ['bid_bond', '投标保证金'],
  ['qualification_review', '资格性审查'],
  ['compliance_review', '符合性检查'],
  ['bid_opening', '开标要求'],
  ['bid_evaluation', '评标要求'],
  ['contract_award', '合同授予与签订'],
  ['contract_termination', '合同解除和终止'],
] as const

const defaultParseConfig = () => ({
  is_default: true,
  items: [
    ...REQUIRED_CONFIG_ITEMS.map(([key, label]) => ({
      key,
      label,
      required: true,
      selected: true,
    })),
    ...OPTIONAL_CONFIG_ITEMS.map(([key, label]) => ({
      key,
      label,
      required: false,
      selected: false,
    })),
  ],
  llm_enabled: false,
  llm_mode: 'validate',
})

// Electron preload API mock（jsdom 环境无 Electron；sidecar.call 按路由返回默认值）
window.bid = {
  app: {
    getVersion: () => Promise.resolve('0.0.0'),
    getUserDataPath: () => Promise.resolve(''),
  },
  update: {
    checkForUpdates: () => Promise.resolve({ ok: true }),
    onStatus: (cb: (payload: unknown) => void) => {
      cb({ status: 'not_available' })
      return () => {}
    },
    onDownloadProgress: () => () => {},
  },
  sidecar: {
    health: () => Promise.resolve({ status: 'healthy' }),
    call: (route: string, payload?: unknown, method?: string) => {
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
          extraction: null,
          score: null,
          docx: null,
          confirmed: null,
        })
      if (route.endsWith('/parse/config')) {
        const base = defaultParseConfig()
        if (method === 'PUT' && payload && typeof payload === 'object') {
          const selected = new Set((payload as { selected?: string[] }).selected ?? [])
          const llmEnabled = Boolean((payload as { llm_enabled?: boolean }).llm_enabled)
          const config = {
            is_default: false,
            items: base.items.map((i) => ({ ...i, selected: selected.has(i.key) })),
            llm_enabled: llmEnabled,
            llm_mode: llmEnabled
              ? ((payload as { llm_mode?: string }).llm_mode ?? 'validate')
              : 'validate',
          }
          return Promise.resolve({
            config,
            reparse_required: false,
            changes: {},
            affected_items: [],
          })
        }
        return Promise.resolve(base)
      }
      if (route.includes('/format/list'))
        return Promise.resolve({
          items: [],
          total: 0,
          confirmed_count: 0,
          missing_count: 0,
          external_count: 0,
          confirmed_at: null,
        })
      return Promise.resolve([])
    },
    stream: () => Promise.resolve({ stage: 'completed', percent: 100, message: '' }),
    cancelTask: () => Promise.resolve({}),
  },
  dialog: {
    openBidFiles: () => Promise.resolve([]),
    openMaterialFiles: () => Promise.resolve([]),
  },
  shell: {
    openDocxFile: () => Promise.resolve({ opened: true, path: '/mock/docx.docx' }),
  },
  shell: {
    openDocxFile: () => Promise.resolve({ opened: true, path: '/mock/docx.docx' }),
  },
  cred: {
    setApiKey: () => Promise.resolve({ success: true }),
    getApiKey: () => Promise.resolve(null),
    hasApiKey: () => Promise.resolve(false),
    clearApiKey: () => Promise.resolve({ success: true }),
  },
} as unknown as BidAPI
