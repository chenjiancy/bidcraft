import { describe, expect, it } from 'vitest'
import { envLabel } from '../lib/format'

describe('envLabel', () => {
  it('dev 返回开发环境', () => {
    expect(envLabel(true)).toBe('开发环境')
  })

  it('prod 返回生产环境', () => {
    expect(envLabel(false)).toBe('生产环境')
  })
})
