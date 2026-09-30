import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderApp, resetAppStore } from './utils'
import { useAppStore } from '../stores/useAppStore'

describe('锁定项 tooltip 命中区', () => {
  beforeEach(() => {
    resetAppStore()
  })

  it('已选项目但未确认时，商务标制作等锁定项在导航中处于 disabled 状态', () => {
    useAppStore.getState().setCurrentEnterprise({ id: 'ent-1', name: '测试企业', agent: '张三' })
    useAppStore.getState().setCurrentProject({ id: 'proj-1', name: '测试项目', agent: '张三' })
    // parseConfirmed / formatConfirmed / materialConfirmed 均保持 false（默认）
    renderApp('/project-home')
    for (const label of ['商务标制作', '素材提取', '标书检查', '模板匹配', '逐章渲染']) {
      expect(screen.getByRole('menuitem', { name: label })).toHaveClass('ant-menu-item-disabled')
    }
  })

  it('锁定项的 tooltip 触发器 span 撑满菜单行宽度', () => {
    useAppStore.getState().setCurrentEnterprise({ id: 'ent-1', name: '测试企业', agent: '张三' })
    useAppStore.getState().setCurrentProject({ id: 'proj-1', name: '测试项目', agent: '张三' })
    renderApp('/project-home')
    // 锁定项的触发器由 AppLayout 渲染，带 data-testid 与 block 宽
    const triggers = screen.queryAllByTestId('nav-locked-tooltip-trigger')
    // 至少有一个锁定项渲染了触发器（商务标制作）
    expect(triggers.length).toBeGreaterThan(0)
    for (const trigger of triggers) {
      expect(trigger).toHaveStyle({ display: 'block', width: '100%' })
    }
  })

  it('所有 tooltip 触发器都位于 ant-menu-item-disabled li 内', () => {
    useAppStore.getState().setCurrentEnterprise({ id: 'ent-1', name: '测试企业', agent: '张三' })
    useAppStore.getState().setCurrentProject({ id: 'proj-1', name: '测试项目', agent: '张三' })
    renderApp('/project-home')
    const triggers = screen.getAllByTestId('nav-locked-tooltip-trigger')
    for (const trigger of triggers) {
      let el = trigger.parentElement
      let foundDisabled = false
      while (el) {
        if (
          el.getAttribute('role') === 'menuitem' &&
          el.classList.contains('ant-menu-item-disabled')
        ) {
          foundDisabled = true
          break
        }
        el = el.parentElement
      }
      expect(foundDisabled).toBe(true)
    }
  })
})
