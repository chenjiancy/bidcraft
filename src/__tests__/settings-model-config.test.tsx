import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderApp, resetAppStore } from './utils'

describe('模型配置页', () => {
  beforeEach(() => {
    resetAppStore()
  })

  it('配置页显示模型配置表单与 API Key 区域', async () => {
    renderApp('/')
    const user = userEvent.setup()
    await user.click(screen.getByRole('menuitem', { name: '配置' }))

    expect(screen.getByText('模型配置')).toBeInTheDocument()
    expect(screen.getByText('供应商')).toBeInTheDocument()
    expect(screen.getByText('Base URL')).toBeInTheDocument()
    expect(screen.getByText('API Key：')).toBeInTheDocument()
  })

  it('可填写模型配置并点击保存', async () => {
    const user = userEvent.setup()
    renderApp('/')
    await user.click(screen.getByRole('menuitem', { name: '配置' }))

    // 等待表单加载
    const modelInput = await screen.findByPlaceholderText('选择或输入模型名（如 gpt-4o）')
    await user.type(modelInput, 'gpt-4o')

    const saveBtn = screen.getByRole('button', { name: '保存配置' })
    await user.click(saveBtn)

    // 保存后应显示成功提示
    expect(await screen.findByText('模型配置已保存')).toBeInTheDocument()
  })

  it('未保存 API Key 时测试连接提示警告', async () => {
    const user = userEvent.setup()
    renderApp('/')
    await user.click(screen.getByRole('menuitem', { name: '配置' }))

    // 等待表单加载
    await screen.findByPlaceholderText('选择或输入模型名（如 gpt-4o）')

    // 未确认外联时点击测试连接 → 弹出首次外联提示
    const testBtn = screen.getByRole('button', { name: '测试连接' })
    await user.click(testBtn)

    expect(await screen.findByText('首次外联提示')).toBeInTheDocument()
  })
})
