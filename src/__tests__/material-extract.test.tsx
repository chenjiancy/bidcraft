import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderApp, resetAppStore } from './utils'
import { useAppStore } from '../stores/useAppStore'

interface Row {
  id: string
  requirement_name: string
  source: string
  source_anchor: string | null
  selected_material_id: string | null
  status: string
  confirmed_at: string | null
  round: number
}

const PENDING_ROW: Row = {
  id: 'it-1',
  requirement_name: '监理资质证书',
  source: 'score_table',
  source_anchor: '评分项: 资质',
  selected_material_id: null,
  status: 'pending',
  confirmed_at: null,
  round: 1,
}

function toList(rows: Row[]) {
  return {
    items: rows,
    total: rows.length,
    pending: rows.filter((r) => r.status === 'pending').length,
    selected: rows.filter((r) => r.status === 'selected').length,
    missing: rows.filter((r) => r.status === 'missing').length,
  }
}

/** 有状态的 material-extract 路由 mock（模拟后端轮次/结论落库）。 */
function makeCallMock(initial: Row[]) {
  let rows = initial.map((r) => ({ ...r }))
  const call = vi.fn((route: string, payload?: unknown, method?: string) => {
    if (route.includes('/material-extract/query')) {
      return Promise.resolve({
        candidates: [
          {
            group_key: '监理资质证书',
            items: [
              {
                id: 'm-1',
                name: '监理资质证书',
                filename: '监理资质证书_P0.jpg',
                file_path: '/lib/1.jpg',
                category: 'qualification',
                valid_until: 'changqi',
                rank: -2,
              },
              {
                id: 'm-2',
                name: '监理资质证书',
                filename: '监理资质证书_P1.jpg',
                file_path: '/lib/2.jpg',
                category: 'qualification',
                valid_until: 'changqi',
                rank: -1,
              },
            ],
          },
        ],
        total: 2,
      })
    }
    if (route.includes('/material-extract/save-round')) {
      const p = payload as {
        changes: { item_id: string; status?: string; selected_material_id?: string }[]
      }
      for (const c of p.changes) {
        rows = rows.map((r) =>
          r.id === c.item_id
            ? {
                ...r,
                status: c.status ?? r.status,
                selected_material_id: c.selected_material_id ?? r.selected_material_id,
              }
            : r,
        )
      }
      return Promise.resolve(toList(rows))
    }
    if (route.includes('/material-extract/confirm')) {
      return Promise.resolve({
        confirmed_at: '2026-09-29T00:00:00Z',
        round: 1,
        item_count: rows.length,
      })
    }
    if (route.includes('/material-extract/import-external')) {
      const p = payload as { file_path: string }
      return Promise.resolve({ id: 'm-ext-1', file_path: p.file_path })
    }
    if (route.includes('/material-extract/items') && method === 'POST') {
      const p = payload as { requirement_name: string }
      const row: Row = {
        id: `it-${rows.length + 1}`,
        requirement_name: p.requirement_name,
        source: 'manual',
        source_anchor: null,
        selected_material_id: null,
        status: 'pending',
        confirmed_at: null,
        round: 1,
      }
      rows = [...rows, row]
      return Promise.resolve(row)
    }
    if (route.includes('/material-extract/new-round')) {
      return Promise.resolve({ round: 2, item_count: rows.length })
    }
    if (route.includes('/material-extract/generate')) {
      return Promise.resolve({ requirement_count: rows.length, round: 1, items: rows })
    }
    if (route.includes('/material-extract')) return Promise.resolve(toList(rows))
    return Promise.resolve([])
  })
  return call
}

/** 渲染提取清单页（已置为 FORMAT_CONFIRMED 解锁态 + 已选项目）。 */
function renderExtractPage(rows: Row[] = [PENDING_ROW]) {
  const callMock = makeCallMock(rows)
  vi.spyOn(window.bid.sidecar, 'call').mockImplementation(callMock as never)
  useAppStore.getState().setCurrentEnterprise({ id: 'ent-1', name: '测试企业', agent: '张三' })
  useAppStore.getState().setCurrentProject({ id: 'proj-1', name: '测试项目', agent: '张三' })
  useAppStore.getState().setParseConfirmed(true)
  useAppStore.getState().setFormatStatus('FORMAT_CONFIRMED')
  renderApp('/extract')
  return callMock
}

/** 按可见文本定位按钮（规避图标 aria-label 影响可访问名）。 */
function buttonByText(label: string): HTMLButtonElement {
  const el = screen.getByText(label)
  const btn = el.closest('button')
  if (!btn) throw new Error(`未找到按钮: ${label}`)
  return btn as HTMLButtonElement
}

describe('Task 16: 素材提取清单', () => {
  beforeEach(() => {
    resetAppStore()
    vi.restoreAllMocks()
  })

  it('TR-16.1: 展示待查清单及来源锚点（评分办法/格式清单）', async () => {
    renderExtractPage()

    await screen.findByText('监理资质证书')
    expect(screen.getByText(/评分办法/)).toBeInTheDocument()
    expect(screen.getByText(/评分项: 资质/)).toBeInTheDocument()
    // 有 pending 项时门禁不放行
    expect(screen.getByText(/仍有 1 项待查/)).toBeInTheDocument()
    expect(buttonByText('确认保存清单')).toBeDisabled()
  })

  it('TR-16.3/16.4/16.9: 查询候选（证件组聚合）→ 选定 → 门禁放行 → 确认保存', async () => {
    const callMock = renderExtractPage()
    await screen.findByText('监理资质证书')

    fireEvent.click(buttonByText('查询匹配'))

    // 多页素材按证件组聚合
    await screen.findByText('2 页')
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(buttonByText('选定并记录'))

    await waitFor(() => expect(screen.getByText(/已选定 1/)).toBeInTheDocument())
    expect(screen.getByText(/待查 0/)).toBeInTheDocument()
    expect(buttonByText('确认保存清单')).not.toBeDisabled()

    fireEvent.click(buttonByText('确认保存清单'))

    await screen.findByText(/提取清单已确认保存/)
    await waitFor(() => {
      const confirmed = callMock.mock.calls.some(
        ([route]) => typeof route === 'string' && route.includes('/material-extract/confirm'),
      )
      expect(confirmed).toBe(true)
    })
    expect(useAppStore.getState().isMaterialConfirmed).toBe(true)
  })

  it('TR-16.5/16.8: 本轮结论以 changes 形式落库（missing 留痕）', async () => {
    const callMock = renderExtractPage()
    await screen.findByText('监理资质证书')

    fireEvent.click(buttonByText('标记缺失'))
    fireEvent.click(buttonByText('保存本轮结论'))

    await waitFor(() => {
      const saveCall = callMock.mock.calls.find(
        ([route]) => typeof route === 'string' && route.includes('/material-extract/save-round'),
      )
      expect(saveCall).toBeDefined()
      const body = saveCall?.[1] as {
        round: number
        changes: { item_id: string; status?: string }[]
      }
      expect(body.round).toBe(1)
      expect(body.changes).toEqual([
        { item_id: 'it-1', status: 'missing', selected_material_id: undefined },
      ])
    })
  })

  it('TR-16.2: 可手工新增需求项', async () => {
    const callMock = renderExtractPage()
    await screen.findByText('监理资质证书')

    fireEvent.click(buttonByText('手工新增需求项'))
    const input = await screen.findByPlaceholderText('如：监理工程师注册证书')
    fireEvent.change(input, { target: { value: '监理工程师注册证书' } })
    fireEvent.click(screen.getByRole('button', { name: /^确\s*定$/ }))

    await waitFor(() => {
      const addCall = callMock.mock.calls.find(
        ([route, , method]) =>
          typeof route === 'string' &&
          route.endsWith('/material-extract/items') &&
          method === 'POST',
      )
      expect(addCall).toBeDefined()
      expect((addCall?.[1] as { requirement_name: string }).requirement_name).toBe(
        '监理工程师注册证书',
      )
    })
    await screen.findByText('监理工程师注册证书')
  })

  it('TR-16.6: A 类——库外文件导入并记为选定', async () => {
    const callMock = renderExtractPage()
    vi.spyOn(window.bid.dialog, 'openMaterialFiles').mockResolvedValue([
      { name: '资质证书.pdf', path: '/outside/资质证书.pdf' },
    ])
    await screen.findByText('监理资质证书')

    fireEvent.click(buttonByText('库外导入'))
    await screen.findByText('库外文件导入')
    fireEvent.click(buttonByText('选择文件并导入'))

    await waitFor(() => {
      const importCall = callMock.mock.calls.find(
        ([route]) =>
          typeof route === 'string' && route.includes('/material-extract/import-external'),
      )
      expect(importCall).toBeDefined()
      expect(importCall?.[1]).toMatchObject({ file_path: '/outside/资质证书.pdf' })
    })
    await waitFor(() => expect(screen.getByText(/已选定 1/)).toBeInTheDocument())
  })

  it('未选择项目时提示先选项目', async () => {
    vi.spyOn(window.bid.sidecar, 'call').mockResolvedValue([] as never)
    useAppStore.getState().setParseConfirmed(true)
    useAppStore.getState().setFormatStatus('FORMAT_CONFIRMED')
    renderApp('/extract')

    await screen.findByText('请先在「企业/项目」中选择一个项目')
  })

  it('TR-16.x: 解析页 FORMAT_CONFIRMED 提供「前往素材提取清单」入口', async () => {
    vi.spyOn(window.bid.sidecar, 'call').mockImplementation(((route: string) => {
      if (route.endsWith('/parse/engine'))
        return Promise.resolve({
          available: true,
          cuda_available: true,
          libreoffice_available: true,
        })
      if (route.endsWith('/parse/status'))
        return Promise.resolve({
          parse_status: 'FORMAT_CONFIRMED',
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
      if (route.endsWith('/parse/config'))
        return Promise.resolve({
          is_default: true,
          items: [{ key: 'tech_score', label: '技术评分要求', required: true, selected: true }],
          llm_enabled: false,
          llm_mode: 'validate',
        })
      return Promise.resolve([])
    }) as never)

    useAppStore.getState().setCurrentEnterprise({ id: 'ent-1', name: '测试企业', agent: '张三' })
    useAppStore.getState().setCurrentProject({ id: 'proj-1', name: '测试项目', agent: '张三' })
    renderApp('/parse')

    await screen.findByText('解析配置')
    await screen.findByText('前往素材提取清单')
  })

  it('回归: PARSE_CONFIRMED 起 /bid 可进入（格式清单复核不被门禁拦截）', async () => {
    vi.spyOn(window.bid.sidecar, 'call').mockImplementation(((route: string) => {
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
    }) as never)

    // PARSE_CONFIRMED：格式清单尚未确认，但商务标模块须可进入完成复核
    useAppStore.getState().setParseConfirmed(true)
    useAppStore.getState().setFormatStatus(undefined)
    renderApp('/bid')

    expect(screen.queryByText('模块未解锁')).not.toBeInTheDocument()
  })
})
