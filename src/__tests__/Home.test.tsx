import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import Home from '../pages/Home'

// 模拟 preload 暴露的 window.bid
vi.stubGlobal('bid', {
  app: {
    getVersion: vi.fn().mockResolvedValue('0.1.0'),
    getUserDataPath: vi.fn().mockResolvedValue('C:/Users/test/AppData/Roaming/BidCraft-dev'),
  },
})

describe('Home', () => {
  it('渲染应用标题', async () => {
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    )
    // 等待 useEffect 中的异步调用全部落定，避免 act 警告
    await waitFor(() => expect(screen.getByText('0.1.0')).toBeInTheDocument())
    expect(screen.getByText('AI标书制作')).toBeInTheDocument()
  })

  it('渲染从主进程获取的版本号', async () => {
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByText('0.1.0')).toBeInTheDocument())
  })
})
