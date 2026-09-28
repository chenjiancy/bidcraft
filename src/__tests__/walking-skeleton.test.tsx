import { screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderApp, resetAppStore } from './utils'
import { useAppStore } from '../stores/useAppStore'

describe('Task 7: Walking Skeleton 端到端', () => {
  beforeEach(() => {
    resetAppStore()
  })

  it('TR-7.2: 未确认解析清单前商务标/标书检查菜单置灰', () => {
    renderApp('/')
    expect(screen.getByRole('menuitem', { name: '商务标制作' })).toHaveClass(
      'ant-menu-item-disabled',
    )
    expect(screen.getByRole('menuitem', { name: '标书检查' })).toHaveClass('ant-menu-item-disabled')
  })

  it('TR-7.1: 选项目→模拟确认→商务标解锁', async () => {
    // 直接设置当前企业和项目（模拟已选项目状态）
    useAppStore.getState().setCurrentEnterprise({ id: 'ent-1', name: '测试企业', agent: '张三' })
    useAppStore.getState().setCurrentProject({ id: 'proj-1', name: '测试项目', agent: '张三' })

    renderApp('/parse')

    // 1. 解析页显示文件上传区
    expect(await screen.findByText(/点击或拖拽招标文件到此处/)).toBeInTheDocument()

    // 2. 商务标制作仍置灰
    expect(screen.getByRole('menuitem', { name: '商务标制作' })).toHaveClass(
      'ant-menu-item-disabled',
    )

    // 3. 模拟确认按钮初始禁用（未上传文件）
    const confirmBtn = screen.getByRole('button', { name: /模拟确认解析清单/ })
    expect(confirmBtn).toBeDisabled()

    // 4. 模拟确认（直接设置状态，实际 UI 需先上传文件）
    useAppStore.getState().setParseConfirmed(true)

    // 5. 商务标制作菜单应解锁（等待重新渲染）
    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: '商务标制作' })).not.toHaveClass(
        'ant-menu-item-disabled',
      )
    })

    // 6. 标书检查菜单也应解锁
    expect(screen.getByRole('menuitem', { name: '标书检查' })).not.toHaveClass(
      'ant-menu-item-disabled',
    )
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
