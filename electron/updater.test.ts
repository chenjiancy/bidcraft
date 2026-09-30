/**
 * initUpdater 集成测试：验证其与 autoUpdater 的交互行为。
 *
 * 策略：mock electron-updater（autoUpdater）和 electron（BrowserWindow），
 * 然后调用 initUpdater，断言 autoUpdater 的调用序列正确。
 */
import { EventEmitter } from 'node:events'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 在 import 之前 mock 模块
vi.mock('electron-updater', () => {
  const emitter = new EventEmitter()
  const mockAutoUpdater = Object.assign(emitter, {
    setFeedURL: vi.fn(),
    autoDownload: false,
    autoInstallOnAppQuit: false,
    checkForUpdates: vi.fn(),
  })
  return { autoUpdater: mockAutoUpdater }
})

vi.mock('electron', () => ({
  BrowserWindow: vi.fn(),
}))

import { initUpdater } from './updater'
import { autoUpdater } from 'electron-updater'
import { UPDATE_CONFIG } from './lib/update-config'

// 每次测试前清空 autoUpdater 的 mock 调用历史与 EventEmitter 监听
beforeEach(() => {
  vi.clearAllMocks()
  ;(autoUpdater as EventEmitter).removeAllListeners()
  ;(autoUpdater as { checkForUpdates: ReturnType<typeof vi.fn> }).checkForUpdates.mockClear()
  ;(autoUpdater as { setFeedURL: ReturnType<typeof vi.fn> }).setFeedURL.mockClear()
})

function makeMockWindow() {
  const sends: Array<{ channel: string; payload?: unknown }> = []
  const webContents = {
    send: vi.fn((channel: string, payload?: unknown) => sends.push({ channel, payload })),
  }
  return { webContents, sends }
}

describe('initUpdater', () => {
  it('调用 setFeedURL 传入正确的 GitHub feed 配置', () => {
    const { webContents } = makeMockWindow()
    initUpdater({ webContents } as never)
    expect(autoUpdater.setFeedURL).toHaveBeenCalledTimes(1)
    expect(autoUpdater.setFeedURL).toHaveBeenCalledWith(UPDATE_CONFIG)
  })

  it('将 autoDownload 设为 true', () => {
    const { webContents } = makeMockWindow()
    initUpdater({ webContents } as never)
    expect(autoUpdater.autoDownload).toBe(true)
  })

  it('将 autoInstallOnAppQuit 设为 true', () => {
    const { webContents } = makeMockWindow()
    initUpdater({ webContents } as never)
    expect(autoUpdater.autoInstallOnAppQuit).toBe(true)
  })

  it('调用 checkForUpdates 触发启动时版本检查', () => {
    const { webContents } = makeMockWindow()
    initUpdater({ webContents } as never)
    expect(autoUpdater.checkForUpdates).toHaveBeenCalledTimes(1)
  })

  it('注册的事件监听被触发时，通过 webContents.send 转发给渲染进程', () => {
    const { webContents, sends } = makeMockWindow()
    initUpdater({ webContents } as never)

    ;(autoUpdater as EventEmitter).emit('checking-for-update')
    ;(autoUpdater as EventEmitter).emit('update-available')
    ;(autoUpdater as EventEmitter).emit('update-downloaded')
    ;(autoUpdater as EventEmitter).emit('error', { message: 'test error' })
    ;(autoUpdater as EventEmitter).emit('download-progress', { percent: 50, bytesPerSecond: 1024 })

    expect(webContents.send).toHaveBeenCalledTimes(5)
    expect(sends).toContainEqual({ channel: 'update:status', payload: { status: 'checking' } })
    expect(sends).toContainEqual({ channel: 'update:status', payload: { status: 'available' } })
    expect(sends).toContainEqual({ channel: 'update:status', payload: { status: 'downloaded' } })
    expect(sends).toContainEqual({
      channel: 'update:status',
      payload: { status: 'error', message: 'test error' },
    })
    expect(sends).toContainEqual({
      channel: 'update:download-progress',
      payload: { percent: 50 },
    })
  })

  it('未触发任何事件时，webContents.send 不被调用', () => {
    const { webContents } = makeMockWindow()
    initUpdater({ webContents } as never)
    expect(webContents.send).not.toHaveBeenCalled()
  })
})
