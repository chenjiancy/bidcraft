import { _electron as electron, expect, test } from '@playwright/test'
import { join } from 'node:path'

test('外壳导航、门禁与主题切换', async () => {
  const app = await electron.launch({ args: [join(__dirname, '..')] })
  const page = await app.firstWindow()

  // 默认进入企业/项目占位页，5 个导航项可见
  await expect(page.getByRole('menuitem', { name: '企业/项目' })).toBeVisible()
  await expect(page.getByText('企业/项目管理')).toBeVisible()
  for (const label of ['招标文件解析', '商务标制作', '标书检查', '配置']) {
    await expect(page.getByRole('menuitem', { name: label })).toBeVisible()
  }

  // 未确认清单前商务标菜单置灰
  await expect(page.getByRole('menuitem', { name: '商务标制作' })).toHaveClass(
    /ant-menu-item-disabled/,
  )

  // 模拟确认清单 → 解锁
  await page.getByRole('menuitem', { name: '招标文件解析' }).click()
  await page.getByRole('button', { name: '模拟确认解析清单（临时）' }).click()
  await expect(page.getByRole('menuitem', { name: '商务标制作' })).not.toHaveClass(
    /ant-menu-item-disabled/,
  )
  await page.getByRole('menuitem', { name: '商务标制作' }).click()
  await expect(page.getByText('商务标制作').first()).toBeVisible()

  // 主题切换：根节点 data-theme 跟随
  await page.getByRole('button', { name: '切换主题' }).click()
  expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('dark')
  await page.getByRole('button', { name: '切换主题' }).click()
  expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('light')

  await app.close()
})
