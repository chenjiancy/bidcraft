import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderApp, resetAppStore } from './utils'
import { useAppStore } from '../stores/useAppStore'

describe('应用外壳与导航', () => {
  beforeEach(() => {
    resetAppStore()
  })

  it('默认路由重定向到企业/项目页；启动页导航仅含企业/项目与底部配置', () => {
    renderApp('/')
    expect(screen.getByRole('button', { name: /新建企业/ })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: '企业/项目' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: '配置' })).toBeInTheDocument()
    // 解析/商务标/标书检查不在首页导航（经项目流程进入）
    for (const label of ['招标文件解析', '商务标制作', '标书检查']) {
      expect(screen.queryByRole('menuitem', { name: label })).not.toBeInTheDocument()
    }
  })

  it('点击导航可在企业/项目与配置页之间切换', async () => {
    const user = userEvent.setup()
    renderApp('/')

    await user.click(screen.getByRole('menuitem', { name: '配置' }))
    expect(screen.getByText('系统配置（占位）')).toBeInTheDocument()

    await user.click(screen.getByRole('menuitem', { name: '企业/项目' }))
    expect(await screen.findByRole('button', { name: /新建企业/ })).toBeInTheDocument()
  })

  it('手工直跳锁定路由时被门禁拦截', () => {
    renderApp('/bid')
    expect(screen.getByText('模块未解锁')).toBeInTheDocument()
  })

  it('确认清单后业务模块解锁、可正常进入', () => {
    useAppStore.getState().setParseConfirmed(true)
    useAppStore.getState().setFormatStatus('FORMAT_CONFIRMED')
    renderApp('/bid')
    expect(screen.getByText('商务标格式清单确认')).toBeInTheDocument()
    expect(screen.queryByText('模块未解锁')).not.toBeInTheDocument()
  })
})
