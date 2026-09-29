import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderApp, resetAppStore } from './utils'
import { useAppStore } from '../stores/useAppStore'

describe('Task 7/13: Walking Skeleton 端到端', () => {
  beforeEach(() => {
    resetAppStore()
  })

  it('TR-7.2: 首页导航无商务标/标书检查入口，未确认清单时路由仍被门禁拦截', () => {
    renderApp('/')
    for (const label of ['招标文件解析', '商务标制作', '标书检查']) {
      expect(screen.queryByRole('menuitem', { name: label })).not.toBeInTheDocument()
    }
    renderApp('/bid')
    expect(screen.getByText('模块未解锁')).toBeInTheDocument()
  })

  it('TR-7.1/13.7: 解析完成→进入复核→确认全部条目→商务标解锁', async () => {
    useAppStore.getState().setCurrentEnterprise({ id: 'ent-1', name: '测试企业', agent: '张三' })
    useAppStore.getState().setCurrentProject({ id: 'proj-1', name: '测试项目', agent: '张三' })

    vi.spyOn(window.bid.dialog, 'openBidFiles').mockResolvedValue([
      { name: '招标文件.pdf', path: 'C:/fake/招标文件.pdf' },
    ])

    // 解析完成后 status 返回 SCORE_PARSED；confirm 后返回 PARSE_CONFIRMED
    let status = 'SCORE_PARSED'
    const callSpy = vi.spyOn(window.bid.sidecar, 'call').mockImplementation((route: string) => {
      if (route.endsWith('/parse/engine'))
        return Promise.resolve({
          available: true,
          cuda_available: true,
          libreoffice_available: true,
        })
      if (route.endsWith('/parse/config'))
        return Promise.resolve({
          is_default: true,
          items: [
            { key: 'project_overview', label: '项目概述', required: true, selected: true },
            { key: 'tech_score', label: '技术评分要求', required: true, selected: true },
          ],
          llm_enabled: false,
          llm_mode: 'validate',
        })
      if (route.endsWith('/parse/status')) {
        return Promise.resolve({
          parse_status: status,
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
      }
      if (route.endsWith('/parse/checklist'))
        return Promise.resolve({
          parse_status: 'PARSE_REVIEW',
          extraction: {
            items: [{ key: 'project_overview', label: '项目概述', selected: true, matches: [] }],
          },
          score: null,
          docx: null,
          confirmed: null,
          review_state: null,
        })
      if (route.endsWith('/parse/review'))
        return Promise.resolve({
          parse_status: 'PARSE_REVIEW',
          review_started_at: '2026-09-29T00:00:00Z',
        })
      if (route.endsWith('/parse/confirm')) {
        status = 'PARSE_CONFIRMED'
        return Promise.resolve({
          parse_status: 'PARSE_CONFIRMED',
          confirmed_at: '2026-09-29T00:00:00Z',
          checklist_path: 'parse/confirmed/parse_checklist.json',
          total_items: 1,
          confirmed_items: 1,
        })
      }
      return Promise.resolve([])
    })
    vi.spyOn(window.bid.sidecar, 'stream').mockResolvedValue({
      stage: 'completed',
      percent: 100,
      message: '',
    })

    renderApp('/parse')

    const pickBtn = await screen.findByRole('button', { name: /选择招标文件/ })
    expect(useAppStore.getState().isParseConfirmed).toBe(false)

    fireEvent.click(pickBtn)
    expect(await screen.findByText('招标文件.pdf')).toBeInTheDocument()

    // 解析完成
    fireEvent.click(screen.getByRole('button', { name: /登记并开始解析/ }))

    // Task 13：解析完成后不再自动解锁，需进入复核
    await waitFor(() => {
      expect(useAppStore.getState().parseStatus).toBe('SCORE_PARSED')
    })
    expect(useAppStore.getState().isParseConfirmed).toBe(false)

    // 进入清单复核
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /进入清单复核/ })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: /进入清单复核/ }))

    // 在复核界面勾选条目并保存
    await waitFor(() => {
      expect(screen.getByText(/已确认 0 \/ 1 条/)).toBeInTheDocument()
    })
    // 点击 checkbox label 触发确认
    const checkboxLabel = screen.getByText(/无匹配项/)
    fireEvent.click(checkboxLabel)
    await waitFor(() => {
      expect(screen.getByText(/已确认 1 \/ 1 条/)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /保存并解锁/ }))

    // 确认后门禁解锁
    await waitFor(() => {
      expect(useAppStore.getState().isParseConfirmed).toBe(true)
    })
    expect(callSpy).toHaveBeenCalledWith(
      expect.stringContaining('/parse/confirm'),
      expect.any(Object),
    )
  })

  it('切换项目时重置解析确认状态', () => {
    useAppStore.setState({ isParseConfirmed: true, parseStatus: 'PARSE_CONFIRMED' })

    useAppStore.getState().setCurrentProject({ id: 'new-proj', name: '新项目', agent: '李四' })
    expect(useAppStore.getState().isParseConfirmed).toBe(false)
    expect(useAppStore.getState().parseStatus).toBe(undefined)
  })

  it('切换企业时重置解析确认状态并清空项目', () => {
    useAppStore.setState({
      isParseConfirmed: true,
      parseStatus: 'PARSE_CONFIRMED',
      currentProject: { id: 'p1', name: 'P1', agent: 'A' },
    })

    useAppStore.getState().setCurrentEnterprise({ id: 'new-ent', name: '新企业', agent: '李四' })
    expect(useAppStore.getState().isParseConfirmed).toBe(false)
    expect(useAppStore.getState().parseStatus).toBe(undefined)
    expect(useAppStore.getState().currentProject).toBe(null)
  })

  it('确认后可进入商务标页面', () => {
    useAppStore.getState().setParseConfirmed(true)
    renderApp('/bid')
    expect(screen.getByText(/素材提取、模板匹配与比对/)).toBeInTheDocument()
  })

  it('重置确认后商务标再次锁定', () => {
    useAppStore.getState().setParseConfirmed(false)
    renderApp('/bid')
    expect(screen.getByText('模块未解锁')).toBeInTheDocument()
  })
})
