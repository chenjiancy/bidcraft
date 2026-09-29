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
  opts: {
    status?: string
    putResult?: Record<string, unknown>
    checkpoint?: Record<string, unknown> | null
    extraction?: Record<string, unknown> | null
    score?: Record<string, unknown> | null
    docx?: Record<string, unknown> | null
    confirmed?: Record<string, unknown> | null
    checklist?: Record<string, unknown> | null
  } = {},
): ReturnType<typeof vi.fn> {
  return vi.fn((route: string, payload?: unknown, method?: string) => {
    if (route.endsWith('/parse/engine'))
      return Promise.resolve({ available: true, cuda_available: true, libreoffice_available: true })
    if (route.endsWith('/parse/status'))
      return Promise.resolve({
        parse_status: opts.status ?? 'INIT',
        running: false,
        sources: {},
        checkpoint: opts.checkpoint ?? null,
        chapters: null,
        dedupe: null,
        extraction: opts.extraction ?? null,
        score: opts.score ?? null,
        docx: opts.docx ?? null,
        confirmed: opts.confirmed ?? null,
      })
    if (route.endsWith('/parse/checklist'))
      return Promise.resolve(
        opts.checklist ?? {
          parse_status: opts.status ?? 'INIT',
          extraction: null,
          score: null,
          docx: null,
          confirmed: null,
          review_state: null,
        },
      )
    if (route.endsWith('/parse/review'))
      return Promise.resolve({
        parse_status: 'PARSE_REVIEW',
        review_started_at: '2026-09-29T00:00:00Z',
      })
    if (route.endsWith('/parse/confirm'))
      return Promise.resolve({
        parse_status: 'PARSE_CONFIRMED',
        confirmed_at: '2026-09-29T00:00:00Z',
        checklist_path: 'parse/confirmed/parse_checklist.json',
        total_items: 1,
        confirmed_items: 1,
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
  opts: {
    status?: string
    putResult?: Record<string, unknown>
    checkpoint?: Record<string, unknown> | null
    extraction?: Record<string, unknown> | null
    score?: Record<string, unknown> | null
    docx?: Record<string, unknown> | null
    confirmed?: Record<string, unknown> | null
    checklist?: Record<string, unknown> | null
  } = {},
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

  it('TR-9.2/TR-10.9: LLM 总开关默认关闭，模式置灰；开启后可选校验，双通道恒禁用', async () => {
    await renderParsePage()

    const llmSwitch = screen.getByRole('switch', { name: '启用 LLM 辅助' })
    expect(llmSwitch).not.toBeChecked()
    const validateRadio = screen.getByRole('radio', { name: '校验模式' })
    const dualRadio = screen.getByRole('radio', { name: /双通道模式/ })
    expect(validateRadio).toBeDisabled()
    expect(dualRadio).toBeDisabled()

    fireEvent.click(llmSwitch)
    await waitFor(() => expect(validateRadio).not.toBeDisabled())
    // TR-10.9：双通道本期不实现，开关打开后仍禁用
    expect(dualRadio).toBeDisabled()
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

  it('TR-9.4: PARSED 后保存变更提示重新解析，点击全部重跑触发 reparse', async () => {
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
    fireEvent.click(screen.getByText('全部重跑').closest('button')!)

    await waitFor(() => {
      expect(streamMock).toHaveBeenCalledTimes(1)
    })
    const [route, body] = streamMock.mock.calls[0]
    expect(route).toContain('/parse/start')
    expect(body).toMatchObject({ reparse: true })
    expect(callMock).toBeDefined()
  })

  it('TR-10.x: 配置变更后定向重跑仅重置受影响项（不触发 reparse=true）', async () => {
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
        affected_items: ['extract:coarse'],
      },
    })
    const streamMock = vi
      .spyOn(window.bid.sidecar, 'stream')
      .mockResolvedValue({ stage: 'completed', percent: 100, message: '' })

    fireEvent.click(screen.getByRole('checkbox', { name: '投标保证金' }))
    fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    await screen.findByText(/解析配置已变更，需重新解析/)
    fireEvent.click(screen.getByText('重新解析受影响项').closest('button')!)

    // 先逐项 retry，再续跑（reparse=false）
    await waitFor(() => {
      const retryCalls = callMock.mock.calls.filter(
        ([route]) => typeof route === 'string' && route.endsWith('/parse/retry'),
      )
      expect(retryCalls).toHaveLength(1)
      expect(retryCalls[0][1]).toEqual({ item: 'extract:coarse' })
    })
    await waitFor(() => expect(streamMock).toHaveBeenCalledTimes(1))
    const [, body] = streamMock.mock.calls[0]
    expect(body).toMatchObject({ reparse: false })
  })

  it('TR-10.6: LLM 开启但无 API Key 时阻断解析并提示', async () => {
    await renderParsePage({
      status: 'PARSED',
      checkpoint: {
        job_type: 'document_parse',
        state: 'success',
        counts: { success: 1 },
        updated_at: '2026-09-29',
        items: [
          { key: 'extract:coarse', label: '要素提取', state: 'success', attempts: 1, error: null },
        ],
      },
    })
    const streamMock = vi.spyOn(window.bid.sidecar, 'stream')

    fireEvent.click(screen.getByRole('switch', { name: '启用 LLM 辅助' }))
    await waitFor(() => expect(screen.getByRole('radio', { name: '校验模式' })).not.toBeDisabled())

    // setup.ts cred.getApiKey 默认返回 null → 应阻断
    const startBtn = screen
      .getAllByRole('button')
      .find((b) => /开始解析|从断点继续解析/.test(b.textContent ?? ''))
    expect(startBtn).toBeDefined()
    fireEvent.click(startBtn!)

    await screen.findByText(/已启用 LLM 辅助，请先在「模型配置」中设置 API Key/)
    expect(streamMock).not.toHaveBeenCalled()
  })

  it('TR-10.1/10.4: PARSED 完成面板展示要素提取摘要', async () => {
    await renderParsePage({
      status: 'PARSED',
      extraction: {
        doc_type: '招标',
        items_total: 9,
        items_extracted: 7,
        red_flags: 2,
        llm: { enabled: true, mode: 'validate', status: 'done' },
      },
    })
    await screen.findByText('要素提取摘要')
    expect(screen.getByText('招标')).toBeInTheDocument()
    expect(screen.getByText(/勾选要素：/)).toHaveTextContent('勾选要素：9 项，成功提取 7 项')
    expect(screen.getByText('2 项')).toBeInTheDocument()
    expect(screen.getByText('done')).toBeInTheDocument()
  })

  it('TR-11.8: SCORE_PARSED 视为解析完成，门禁未解锁需进入复核（Task 13）', async () => {
    await renderParsePage({ status: 'SCORE_PARSED' })
    await screen.findByText('解析配置')
    expect(screen.getByText('SCORE_PARSED')).toBeInTheDocument()
    // Task 13：SCORE_PARSED 不再自动解锁，显示"进入清单复核"按钮
    expect(screen.getByRole('button', { name: /进入清单复核/ })).toBeInTheDocument()
    expect(screen.queryByText(/解析清单已确认/)).not.toBeInTheDocument()
  })

  it('TR-11.5/11.6: 评分表摘要展示大类/合计/结构校验，合计≠100 标红', async () => {
    await renderParsePage({
      status: 'SCORE_PARSED',
      score: {
        categories: 3,
        total_score: 95,
        score_ok: false,
        red_flags: 1,
        schema_validated: true,
        llm: { status: 'done' },
      },
    })
    await screen.findByText('评分表摘要')
    expect(screen.getByText('3 个')).toBeInTheDocument()
    expect(screen.getByText(/≠100，请核对/)).toBeInTheDocument()
    expect(screen.getByText('1 项')).toBeInTheDocument()
    expect(screen.getByText('已通过')).toBeInTheDocument()
    expect(screen.getByText('done')).toBeInTheDocument()
  })

  it('TR-12.4/12.5: 投标文件格式摘要展示导出数量、封面与完成状态', async () => {
    await renderParsePage({
      status: 'SCORE_PARSED',
      docx: {
        sources: 1,
        files: 3,
        cover: true,
        completed: true,
        errors: 0,
        red_flags: 0,
        missing_format_sources: [],
      },
    })
    await screen.findByText('投标文件格式（逐章 docx）')
    expect(screen.getByText('3 个')).toBeInTheDocument()
    expect(screen.getByText('已导出')).toBeInTheDocument()
    expect(screen.getByText('已完成')).toBeInTheDocument()
  })

  it('TR-12/决策3A: 无格式章时提示未识别来源，导出为 0 不报错', async () => {
    await renderParsePage({
      status: 'SCORE_PARSED',
      docx: {
        sources: 1,
        files: 0,
        cover: false,
        completed: true,
        errors: 0,
        red_flags: 0,
        missing_format_sources: ['无格式章'],
      },
    })
    await screen.findByText('投标文件格式（逐章 docx）')
    expect(screen.getAllByText('无')).toHaveLength(2)
    expect(screen.getByText(/未识别到「投标文件格式」章节：无格式章/)).toBeInTheDocument()
  })
})
