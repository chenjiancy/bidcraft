import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderApp, resetAppStore } from './utils'
import { useAppStore } from '../stores/useAppStore'

describe('应用外壳与导航', () => {
  beforeEach(() => {
    resetAppStore()
  })

  it('默认路由重定向到企业/项目页，且 5 个导航项全部可见', () => {
    renderApp('/')
    expect(screen.getByRole('button', { name: /新建企业/ })).toBeInTheDocument()
    for (const label of ['企业/项目', '招标文件解析', '商务标制作', '标书检查', '配置']) {
      expect(screen.getByRole('menuitem', { name: label })).toBeInTheDocument()
    }
  })

  it('点击导航可在各模块占位页之间切换', async () => {
    const user = userEvent.setup()
    renderApp('/')

    await user.click(screen.getByRole('menuitem', { name: '配置' }))
    expect(screen.getByText('系统配置（占位）')).toBeInTheDocument()

    await user.click(screen.getByRole('menuitem', { name: '招标文件解析' }))
    // 用页面独有描述断言（菜单中也有"招标文件解析"文字）
    expect(await screen.findByText(/PDF \/ Word \/ 扫描件上传/)).toBeInTheDocument()

    await user.click(screen.getByRole('menuitem', { name: '企业/项目' }))
    expect(await screen.findByRole('button', { name: /新建企业/ })).toBeInTheDocument()
  })

  it('未确认清单前商务标制作/标书检查菜单项置灰', () => {
    renderApp('/')
    const bidItem = screen.getByRole('menuitem', { name: '商务标制作' })
    const checkItem = screen.getByRole('menuitem', { name: '标书检查' })
    expect(bidItem).toHaveClass('ant-menu-item-disabled')
    expect(checkItem).toHaveClass('ant-menu-item-disabled')
  })

  it('手工直跳锁定路由时被门禁拦截', () => {
    renderApp('/bid')
    expect(screen.getByText('模块未解锁')).toBeInTheDocument()
  })

  it('确认清单后业务模块解锁、可正常进入', () => {
    useAppStore.getState().setParseConfirmed(true)
    renderApp('/bid')
    expect(screen.getByText(/素材提取、模板匹配与比对/)).toBeInTheDocument()
    expect(screen.queryByText('模块未解锁')).not.toBeInTheDocument()
  })
})
