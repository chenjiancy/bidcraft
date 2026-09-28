import { describe, expect, it } from 'vitest'
import { getFreePort } from './net-utils'

describe('getFreePort', () => {
  it('返回合法端口且连续两次不相同', async () => {
    const port1 = await getFreePort()
    const port2 = await getFreePort()

    expect(port1).toBeGreaterThan(0)
    expect(port1).toBeLessThanOrEqual(65535)
    expect(Number.isInteger(port1)).toBe(true)
    expect(port1).not.toBe(port2)
  })
})
