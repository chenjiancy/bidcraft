/**
 * main.ts 启动链路单元测试：验证侧边车就绪后才显示窗口。
 *
 * 策略：
 * - 使用 vi.hoisted() 声明共享 mock 变量，确保 vi.resetModules() 后仍可访问
 * - whenReady 返回的 Promise 由全局 __resolveWhenReady 控制解析时机
 * - BrowserWindow mock 用实际构造函数实现，支持 new 实例化及 loadFile/loadURL
 * - mock startSidecar 的成功/失败 Promise，断言后续副作用
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

// vi.hoisted：在模块执行前分配，vi.resetModules() 后仍可通过 import 访问
const mocks = vi.hoisted(() => ({
  startSidecar: vi.fn(),
  stopSidecar: vi.fn(),
  resolveWhenReady: null as (() => void) | null,
}))

// ---------- 在每个测试前重置 mock 状态 ----------
beforeEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
  mocks.resolveWhenReady = null
  delete (globalThis as Record<string, unknown>).__resolveWhenReady
})

// ---------- mock electron ----------
vi.mock('electron', () => {
  // BrowserWindow 必须是一个真正的构造函数，支持 new 实例化
  class MockBrowserWindow {
    on = vi.fn()
    webContents = {
      setWindowOpenHandler: vi.fn(),
      send: vi.fn(),
    }
    show = vi.fn()
    loadFile = vi.fn()
    loadURL = vi.fn()
  }
  // vi.fn 包装构造函数，使其可以被 count
  const BrowserWindowMock = vi.fn(function BrowserWindow() {
    return new MockBrowserWindow()
  })
  // 让 vitest 的 spyOn 识别这是一个 class
  BrowserWindowMock.prototype = MockBrowserWindow.prototype

  // whenReady 返回的 Promise 的 resolve 函数注入到 mocks.resolveWhenReady
  const appMock = {
    getPath: vi.fn(() => '/fake/user/data'),
    isPackaged: false,
    setName: vi.fn(),
    whenReady: vi.fn(() => {
      return new Promise<void>((resolve) => {
        mocks.resolveWhenReady = resolve
        ;(globalThis as Record<string, unknown>).__resolveWhenReady = resolve
      })
    }),
    on: vi.fn(),
    quit: vi.fn(),
  }
  return {
    app: appMock,
    BrowserWindow: BrowserWindowMock,
    ipcMain: { handle: vi.fn() },
    dialog: { showErrorBox: vi.fn(), showOpenDialog: vi.fn() },
    shell: { openPath: vi.fn() },
    session: { getDefaultSession: vi.fn(() => ({ invalidateCertificateError: vi.fn() })) },
  }
})

// ---------- mock electron-updater ----------
vi.mock('electron-updater', () => ({
  autoUpdater: {
    setFeedURL: vi.fn(),
    autoDownload: false,
    autoInstallOnAppQuit: false,
    checkForUpdates: vi.fn(),
  },
}))

// ---------- mock ./sidecar ----------
vi.mock('./sidecar', () => ({
  startSidecar: (...args: unknown[]) => mocks.startSidecar(...args),
  stopSidecar: (...args: unknown[]) => mocks.stopSidecar(...args),
  getSidecarHandle: vi.fn(() => null),
  getSidecarStatus: vi.fn(() => 'stopped'),
  requireSidecarHandle: vi.fn(() => {
    throw new Error('sidecar 尚未启动')
  }),
}))

/** 触发 whenReady Promise 解析，驱动 main.ts 内的启动链继续执行 */
async function triggerWhenReady() {
  if (mocks.resolveWhenReady) mocks.resolveWhenReady()
  // 等待微任务（Promise chain 中的 nextTick）
  await new Promise((r) => setTimeout(r, 10))
}

// ---------- 辅助：获取被 mock 的 Electron API ----------
async function getElectronMocks() {
  const electron = await import('electron')
  return {
    BrowserWindow: electron.BrowserWindow as unknown as ReturnType<typeof vi.fn>,
    app: electron.app as unknown as { quit: ReturnType<typeof vi.fn> },
    dialog: electron.dialog as unknown as { showErrorBox: ReturnType<typeof vi.fn> },
  }
}

// ---------- 测试 ----------

describe('main.ts 侧边车启动链', () => {
  it('sidecar 就绪后调用 createWindow（新 BrowserWindow），不调用 app.quit', async () => {
    mocks.startSidecar.mockResolvedValue({ port: 19876, token: 'abc123' })

    await import('./main')
    await triggerWhenReady()

    const { BrowserWindow, app } = await getElectronMocks()
    expect(BrowserWindow).toHaveBeenCalled()
    expect(app.quit).not.toHaveBeenCalled()
  })

  it('sidecar 启动失败时调用 dialog.showErrorBox 并执行 app.quit', async () => {
    mocks.startSidecar.mockRejectedValue(new Error('sidecar 启动超时'))

    await import('./main')
    await triggerWhenReady()

    const { app, dialog } = await getElectronMocks()
    expect(dialog.showErrorBox).toHaveBeenCalledWith(
      '侧边车启动失败',
      expect.stringContaining('侧边车启动失败'),
    )
    expect(app.quit).toHaveBeenCalled()
  })

  it('sidecar 启动失败时 showErrorBox 和 quit 被调用，且 createWindow 不被调用', async () => {
    mocks.startSidecar.mockRejectedValue(new Error('启动失败'))

    await import('./main')
    await triggerWhenReady()

    const { BrowserWindow, app, dialog } = await getElectronMocks()
    expect(BrowserWindow).not.toHaveBeenCalled()
    expect(dialog.showErrorBox).toHaveBeenCalled()
    expect(app.quit).toHaveBeenCalled()
  })
})
