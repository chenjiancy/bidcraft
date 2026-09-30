import { describe, expect, it } from 'vitest'
import { UPDATE_CONFIG, UPDATE_STRATEGY } from './update-config'

describe('UPDATE_CONFIG', () => {
  it('provider 为 github', () => {
    expect(UPDATE_CONFIG.provider).toBe('github')
  })

  it('owner 为项目仓库所有者', () => {
    expect(UPDATE_CONFIG.owner).toBe('chenjiancy')
  })

  it('repo 为 bidcraft', () => {
    expect(UPDATE_CONFIG.repo).toBe('bidcraft')
  })

  it('类型上声明为 Readonly，TypeScript 不允许赋值', () => {
    // @ts-expect-error - 故意写只读字段，TypeScript 编译期应拒绝
    const _wrote: string = UPDATE_CONFIG.owner
    expect(_wrote).toBe('chenjiancy')
  })
})

describe('UPDATE_STRATEGY', () => {
  it('autoDownload 为 true（静默后台下载）', () => {
    expect(UPDATE_STRATEGY.autoDownload).toBe(true)
  })

  it('autoInstallOnAppQuit 为 true（退出时自动安装）', () => {
    expect(UPDATE_STRATEGY.autoInstallOnAppQuit).toBe(true)
  })
})
