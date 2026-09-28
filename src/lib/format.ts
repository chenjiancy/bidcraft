/** 环境标签（最小纯函数，供单元测试基线）。 */
export function envLabel(isDev: boolean): string {
  return isDev ? '开发环境' : '生产环境'
}
