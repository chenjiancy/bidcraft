import { fireEvent, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderApp, resetAppStore } from './utils'
import { useAppStore } from '../stores/useAppStore'

describe('Task 7: Walking Skeleton 端到端', () => {
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

  it('TR-7.1: 选项目→登记招标文件→解析完成→商务标解锁（Task 8 真实链路）', async () => {
    // 直接设置当前企业和项目（模拟已选项目状态）
    useAppStore.getState().setCurrentEnterprise({ id: 'ent-1', name: '测试企业', agent: '张三' })
    useAppStore.getState().setCurrentProject({ id: 'proj-1', name: '测试项目', agent: '张三' })

    // 文件对话框返回一个本机文件；sidecar.stream mock 直接返回 completed
    vi.spyOn(window.bid.dialog, 'openBidFiles').mockResolvedValue([
      { name: '招标文件.pdf', path: 'C:/fake/招标文件.pdf' },
    ])

    renderApp('/parse')

    // 1. 解析页加载完成（引擎探针 + 状态查询），门禁未解锁、无业务入口按钮
    const pickBtn = await screen.findByRole('button', { name: /选择招标文件/ })
    expect(useAppStore.getState().isParseConfirmed).toBe(false)
    expect(screen.queryByRole('button', { name: '前往商务标制作' })).not.toBeInTheDocument()

    // 2. 选择本机招标文件
    fireEvent.click(pickBtn)
    expect(await screen.findByText('招标文件.pdf')).toBeInTheDocument()

    // 3. 登记并开始解析（mock SSE 立即 completed）
    fireEvent.click(screen.getByRole('button', { name: /登记并开始解析/ }))

    // 4. 解析完成后门禁解锁：出现前往商务标制作/标书检查入口按钮
    await waitFor(() => {
      expect(useAppStore.getState().isParseConfirmed).toBe(true)
    })
    const bidEntry = await screen.findByRole('button', { name: '前往商务标制作' })
    expect(screen.getByRole('button', { name: '前往标书检查' })).toBeInTheDocument()

    // 5. 点击入口可进入商务标页面（导航菜单已无此入口，靠解析页按钮进入）
    fireEvent.click(bidEntry)
    expect(await screen.findByText(/素材提取、模板匹配与比对/)).toBeInTheDocument()
  })

  it('切换项目时重置解析确认状态', () => {
    useAppStore.setState({ isParseConfirmed: true })

    useAppStore.getState().setCurrentProject({ id: 'new-proj', name: '新项目', agent: '李四' })
    expect(useAppStore.getState().isParseConfirmed).toBe(false)
  })

  it('切换企业时重置解析确认状态并清空项目', () => {
    useAppStore.setState({
      isParseConfirmed: true,
      currentProject: { id: 'p1', name: 'P1', agent: 'A' },
    })

    useAppStore.getState().setCurrentEnterprise({ id: 'new-ent', name: '新企业', agent: '李四' })
    expect(useAppStore.getState().isParseConfirmed).toBe(false)
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
