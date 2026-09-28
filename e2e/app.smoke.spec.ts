import { _electron as electron, expect, test } from '@playwright/test'
import { join } from 'node:path'

// Electron 冒烟（prod 构建产物）：启动窗口并断言生产环境标识
test('应用启动并显示 BidCraftApp 标识', async () => {
  const app = await electron.launch({ args: [join(__dirname, '..')] })
  const page = await app.firstWindow()
  await expect(page.locator('body')).toContainText('BidCraftApp')
  await app.close()
})
