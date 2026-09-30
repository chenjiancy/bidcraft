/**
 * 自动更新事件分发器：将 autoUpdater 事件转发给渲染进程。
 *
 * 纯函数，不依赖 Electron；测试时注入 mock send 即可断言事件内容。
 */
export interface UpdateSendFn {
  (channel: string, payload?: unknown): void
}

export interface AutoUpdaterEvents {
  on(event: string, listener: (...args: unknown[]) => void): this
  emit(event: string, ...args: unknown[]): boolean
}

/**
 * 为 autoUpdater 注册全部事件监听，通过 send 向渲染进程转发。
 *
 * 事件 → IPC 通道映射：
 *   checking-for-update   → update:status { status: 'checking' }
 *   update-available      → update:status { status: 'available' }
 *   update-not-available  → update:status { status: 'not_available' }
 *   update-downloaded     → update:status { status: 'downloaded' }
 *   error                 → update:status { status: 'error', message }
 *   download-progress     → update:download-progress { percent }
 */
export function registerUpdaterEvents(emitter: AutoUpdaterEvents, send: UpdateSendFn): void {
  emitter.on('checking-for-update', () => send('update:status', { status: 'checking' }))

  emitter.on('update-available', () => send('update:status', { status: 'available' }))

  emitter.on('update-not-available', () => send('update:status', { status: 'not_available' }))

  emitter.on('download-progress', (progress: { percent: number; bytesPerSecond: number }) =>
    send('update:download-progress', { percent: Math.round(progress.percent) }),
  )

  emitter.on('update-downloaded', () => send('update:status', { status: 'downloaded' }))

  emitter.on('error', (err: { message: string }) =>
    send('update:status', { status: 'error', message: err.message }),
  )
}
