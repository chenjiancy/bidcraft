/**
 * 窗口外观配置单元测试。
 *
 * 测试策略：supportsAcrylic() 接受可选 deps 参数，测试时直接注入 platform
 * 与 osRelease，完全避免 vi.mock / vi.resetModules 的坑。
 */
import { release } from 'node:os'
import { describe, expect, it } from 'vitest'
import { supportsAcrylic, TITLEBAR_HEIGHT } from './window-config'

describe('TITLEBAR_HEIGHT', () => {
  it('为正整数，且等于主进程约定值', () => {
    expect(TITLEBAR_HEIGHT).toBe(42)
    expect(Number.isInteger(TITLEBAR_HEIGHT)).toBe(true)
    expect(TITLEBAR_HEIGHT).toBeGreaterThan(0)
  })
})

describe('supportsAcrylic', () => {
  it('非 Windows 平台一律返回 false', () => {
    expect(supportsAcrylic({ platform: 'darwin', osRelease: () => '10.0.0' })).toBe(false)
    expect(supportsAcrylic({ platform: 'linux', osRelease: () => '5.15.0' })).toBe(false)
  })

  it('Windows 10 build 19041 不支持 Acrylic', () => {
    expect(supportsAcrylic({ platform: 'win32', osRelease: () => '10.0.19041' })).toBe(false)
  })

  it('Windows 11 build 22000（最低门槛）支持 Acrylic', () => {
    expect(supportsAcrylic({ platform: 'win32', osRelease: () => '10.0.22000' })).toBe(true)
  })

  it('Windows 11 build 22621（23H2）支持 Acrylic', () => {
    expect(supportsAcrylic({ platform: 'win32', osRelease: () => '10.0.22621' })).toBe(true)
  })

  it('Windows 10 1809 build 17763 不支持 Acrylic', () => {
    expect(supportsAcrylic({ platform: 'win32', osRelease: () => '10.0.17763' })).toBe(false)
  })

  it('build 恰好等于 21999 时不触发 Acrylic', () => {
    expect(supportsAcrylic({ platform: 'win32', osRelease: () => '10.0.21999' })).toBe(false)
  })

  it('build 远大于 22000 时仍支持 Acrylic', () => {
    expect(supportsAcrylic({ platform: 'win32', osRelease: () => '10.0.26100' })).toBe(true)
  })

  it('未传 deps 时使用全局 process.platform', () => {
    // 仅在 win32 机器上期望 true，其他平台期望 false——验证无参分支正常
    const result = supportsAcrylic()
    const expected = process.platform === 'win32' && Number(release().split('.')[2] ?? 0) >= 22000
    expect(result).toBe(expected)
  })
})
