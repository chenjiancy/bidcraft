import { type AddressInfo, createServer } from 'node:net'

/**
 * 让操作系统分配一个当前空闲的 TCP 端口（仅探测 127.0.0.1）。
 * 注意：返回后存在极小的竞态窗口，sidecar 会立即绑定该端口。
 */
export function getFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.unref()
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address() as AddressInfo
      server.close(() => resolve(port))
    })
  })
}
