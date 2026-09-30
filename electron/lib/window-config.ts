/**
 * 窗口外观配置：磨玻璃（Acrylic）支持检测与标题栏高度常量。
 *
 * 独立于 electron 主进程副作用，便于在 vitest node 环境下单测。
 * main.ts 应从这里导入，而不是直接内联 os.release 探测逻辑。
 *
 * 测试时可通过 deps 参数注入 process/os 以控制平台与构建号。
 */
import { release, type Platform } from 'node:os'

/** 自定义标题栏高度（px），与渲染层 TitleBar 组件保持一致 */
export const TITLEBAR_HEIGHT = 42

interface Deps {
  platform: Platform | string
  osRelease: () => string
}

/**
 * Windows 11（build >= 22000）提供 Acrylic 系统材质。
 * 更早的 Windows 版本会静默忽略 backgroundMaterial 参数，由渲染层渐变背景兜底。
 * 非 Windows 平台不支持。
 *
 * @param deps - 测试时注入；生产时传空对象以使用全局 process/os
 */
export function supportsAcrylic(deps?: Partial<Deps>): boolean {
  const platform = deps?.platform ?? process.platform
  if (platform !== 'win32') return false
  const releaseFn = deps?.osRelease ?? release
  const build = Number(releaseFn().split('.')[2] ?? 0)
  return build >= 22000
}
