import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderApp, resetAppStore } from './utils'

describe('明暗双主题', () => {
  beforeEach(() => {
    resetAppStore()
  })

  it('默认为亮色，根节点 data-theme=light', () => {
    renderApp('/')
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('点击主题切换按钮后根节点变为 dark，再点恢复 light', async () => {
    const user = userEvent.setup()
    renderApp('/')

    await user.click(screen.getByRole('button', { name: '切换主题' }))
    expect(document.documentElement.dataset.theme).toBe('dark')

    await user.click(screen.getByRole('button', { name: '切换主题' }))
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('配置页 Segmented 可切换主题', async () => {
    const user = userEvent.setup()
    renderApp('/settings')

    await user.click(screen.getByText('暗色'))
    expect(document.documentElement.dataset.theme).toBe('dark')

    await user.click(screen.getByText('亮色'))
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
