import { _electron as electron, expect, test } from '@playwright/test'
import { join } from 'node:path'

test('外壳导航、门禁与主题切换', async () => {
  const app = await electron.launch({ args: [join(__dirname, '..')] })
  const page = await app.firstWindow()

  // 默认进入企业/项目页，导航仅含企业/项目 + 底部配置
  await expect(page.getByRole('menuitem', { name: '企业/项目' })).toBeVisible()
  await expect(page.getByRole('button', { name: '新建企业' })).toBeVisible()
  await expect(page.getByRole('menuitem', { name: '配置' })).toBeVisible()
  // 解析/商务标/标书检查不在首页导航（经项目流程进入）
  for (const label of ['招标文件解析', '商务标制作', '标书检查']) {
    await expect(page.getByRole('menuitem', { name: label })).not.toBeVisible()
  }

  // 主题切换：根节点 data-theme 跟随
  await page.getByRole('button', { name: '切换主题' }).click()
  expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('dark')
  await page.getByRole('button', { name: '切换主题' }).click()
  expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('light')

  await app.close()
})
