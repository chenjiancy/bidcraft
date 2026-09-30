// 验证 tooltip：hover 锁定的导航项，截取 tooltip 弹出状态
// 用法: node scripts/verify-tooltip.mjs
import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })

  // 1. 注入「已选项目但未确认解析」状态
  await page.goto(BASE)
  await page.evaluate(() => {
    localStorage.setItem(
      'bidcraft-ui',
      JSON.stringify({
        state: {
          themeMode: 'light',
          currentEnterprise: { id: 'ent-1', name: '测试企业', agent: '张三' },
          currentProject: { id: 'proj-1', name: '测试项目', agent: '张三' },
          isParseConfirmed: false,
          parseStatus: undefined,
          isFormatListConfirmed: false,
          formatStatus: undefined,
          materialStatus: undefined,
          isMaterialConfirmed: false,
        },
        version: 0,
      }),
    )
  })
  await page.reload()
  await page.waitForTimeout(1500)

  // 2. hover「商务标制作」（disabled 项）
  const bidItem = page.locator('li[role="menuitem"]:has-text("商务标制作")').first()
  await bidItem.hover()
  await page.waitForTimeout(800) // 等 tooltip 出现
  await page.screenshot({ path: 'screenshot-tooltip-bid.png', fullPage: false })

  // 3. hover「模板匹配」（disabled 项）
  const matchItem = page.locator('li[role="menuitem"]:has-text("模板匹配")').first()
  await matchItem.hover()
  await page.waitForTimeout(800)
  await page.screenshot({ path: 'screenshot-tooltip-match.png', fullPage: false })

  // 4. hover「逐章渲染」（disabled 项）
  const renderItem = page.locator('li[role="menuitem"]:has-text("逐章渲染")').first()
  await renderItem.hover()
  await page.waitForTimeout(800)
  await page.screenshot({ path: 'screenshot-tooltip-render.png', fullPage: false })

  await browser.close()
  console.log('OK: 3 tooltip screenshots saved')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
