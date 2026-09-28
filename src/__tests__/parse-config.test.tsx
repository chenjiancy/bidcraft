import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderApp, resetAppStore } from './utils'
import { useAppStore } from '../stores/useAppStore'

const REQUIRED_LABELS = [
  '项目概述',
  '技术评分要求',
  '项目信息',
  '甲方信息',
  '响应文件要求',
  '代理机构信息',
  '商务评分要求',
  '无效标与废标项',
]
const OPTIONAL_LABELS = [
  '交货和服务要求',
  '采购清单',
  '投标关键节点',
  '投标保证金',
  '资格性审查',
  '符合性检查',
  '开标要求',
  '评标要求',
  '合同授予与签订',
  '合同解除和终止',
]

/** 按 setup.ts 默认规则构造可定制的 call mock */
function makeCallMock(
  opts: { status?: string; putResult?: Record<string, unknown> } = {},
): ReturnType<typeof vi.fn> {
  return vi.fn((route: string, payload?: unknown, method?: string) => {
    if (route.endsWith('/parse/engine'))
      return Promise.resolve({ available: true, cuda_available: true, libreoffice_available: true })
    if (route.endsWith('/parse/status'))
      return Promise.resolve({
        parse_status: opts.status ?? 'INIT',
        running: false,
        sources: {},
        checkpoint: null,
        chapters: null,
        dedupe: null,
      })
    if (route.endsWith('/parse/config') && method === 'PUT') {
      const p = (payload ?? {}) as { selected?: string[]; llm_enabled?: boolean; llm_mode?: string }
      const defaultItems = [...REQUIRED_LABELS, ...OPTIONAL_LABELS]
      const selected = new Set(p.selected ?? REQUIRED_LABELS)
      const llmEnabled = Boolean(p.llm_enabled)
      return Promise.resolve(
        opts.putResult ?? {
          config: {
            is_default: false,
            items: defaultItems.map((label, i) => ({
              key: label,
              label,
              required: i < REQUIRED_LABELS.length,
              selected: selected.has(label),
            })),
            llm_enabled: llmEnabled,
            llm_mode: llmEnabled ? (p.llm_mode ?? 'validate') : 'validate',
          },
          reparse_required: false,
          changes: {},
          affected_items: [],
        },
      )
    }
    if (route.endsWith('/parse/config')) {
      return Promise.resolve({
        is_default: true,
        items: [...REQUIRED_LABELS, ...OPTIONAL_LABELS].map((label, i) => ({
          key: label,
          label,
          required: i < REQUIRED_LABELS.length,
          selected: i < REQUIRED_LABELS.length,
        })),
        llm_enabled: false,
        llm_mode: 'validate',
      })
    }
    return Promise.resolve([])
  })
}

async function renderParsePage(
  opts: { status?: string; putResult?: Record<string, unknown> } = {},
) {
  const callMock = makeCallMock(opts)
  vi.spyOn(window.bid.sidecar, 'call').mockImplementation(callMock as never)
  useAppStore.getState().setCurrentEnterprise({ id: 'ent-1', name: '测试企业', agent: '张三' })
  useAppStore.getState().setCurrentProject({ id: 'proj-1', name: '测试项目', agent: '张三' })
  renderApp('/parse')
  await screen.findByText('解析配置')
  return callMock
}

describe('Task 9: 解析配置面板', () => {
  beforeEach(() => {
    resetAppStore()
    vi.restoreAllMocks()
  })

  it('TR-9.1: 8 关键项必选不可取消，10 其他项可勾选', async () => {
    await renderParsePage()

    for (const label of REQUIRED_LABELS) {
      const cb = screen.getByRole('checkbox', { name: label })
      expect(cb).toBeChecked()
      expect(cb).toBeDisabled()
    }
    for (const label of OPTIONAL_LABELS) {
      const cb = screen.getByRole('checkbox', { name: label })
      expect(cb).not.toBeChecked()
      expect(cb).not.toBeDisabled()
    }
  })

  it('TR-9.2: LLM 总开关默认关闭，模式置灰；开启后可选校验/双通道', async () => {
    await renderParsePage()

    const llmSwitch = screen.getByRole('switch', { name: '启用 LLM 辅助' })
    expect(llmSwitch).not.toBeChecked()
    const validateRadio = screen.getByRole('radio', { name: '校验模式' })
    const dualRadio = screen.getByRole('radio', { name: '双通道模式' })
    expect(validateRadio).toBeDisabled()
    expect(dualRadio).toBeDisabled()

    fireEvent.click(llmSwitch)
    await waitFor(() => expect(validateRadio).not.toBeDisabled())
    expect(dualRadio).not.toBeDisabled()
    fireEvent.click(dualRadio)
    expect(dualRadio).toBeChecked()
  })

  it('TR-9.3: 勾选其他项保存后以 PUT 落库（关键项必带、LLM 默认关）', async () => {
    const callMock = await renderParsePage()

    fireEvent.click(screen.getByRole('checkbox', { name: '投标保证金' }))
    fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    await waitFor(() => {
      const putCalls = callMock.mock.calls.filter(([, , method]) => method === 'PUT')
      expect(putCalls).toHaveLength(1)
    })
    const putCall = callMock.mock.calls.find(([, , method]) => method === 'PUT')
    expect(putCall?.[0]).toContain('/parse/config')
    const payload = putCall?.[1] as { selected: string[]; llm_enabled: boolean; llm_mode: string }
    expect(payload.llm_enabled).toBe(false)
    expect(payload.selected).toHaveLength(REQUIRED_LABELS.length + 1)
    // mock 按 label 匹配：8 关键项 label 全部在 selected
    for (const label of REQUIRED_LABELS) expect(payload.selected).toContain(label)
    expect(payload.selected).toContain('投标保证金')
  })

  it('TR-9.4: PARSED 后保存变更提示重新解析，点击触发 reparse', async () => {
    const callMock = await renderParsePage({
      status: 'PARSED',
      putResult: {
        config: {
          is_default: false,
          items: [...REQUIRED_LABELS, ...OPTIONAL_LABELS].map((label, i) => ({
            key: label,
            label,
            required: i < REQUIRED_LABELS.length,
            selected: i < REQUIRED_LABELS.length || label === '投标保证金',
          })),
          llm_enabled: false,
          llm_mode: 'validate',
        },
        reparse_required: true,
        changes: { selected_added: ['bid_bond'] },
        affected_items: [],
      },
    })
    const streamMock = vi
      .spyOn(window.bid.sidecar, 'stream')
      .mockResolvedValue({ stage: 'completed', percent: 100, message: '' })

    fireEvent.click(screen.getByRole('checkbox', { name: '投标保证金' }))
    fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    await screen.findByText(/解析配置已变更，需重新解析/)
    // 注：按钮 loading 图标的 aria-label 会改变可访问名，改用文本定位规避
    fireEvent.click(screen.getByText('重新解析全部').closest('button')!)

    await waitFor(() => {
      expect(streamMock).toHaveBeenCalledTimes(1)
    })
    const [route, body] = streamMock.mock.calls[0]
    expect(route).toContain('/parse/start')
    expect(body).toMatchObject({ reparse: true })
    expect(callMock).toBeDefined()
  })
})
