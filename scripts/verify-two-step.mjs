// 验证 workspace 两步引导：未选企业时隐藏项目区域，选中后展示
// 用法: node scripts/verify-two-step.mjs
import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })

  // 1. 未选企业状态：应只有企业卡片，项目区域显示提示文案
  await page.goto(BASE)
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await page.waitForTimeout(1500)
  await page.screenshot({ path: 'screenshot-twostep-no-ent.png', fullPage: true })
  console.log('1. no-ent screenshot saved')

  // 2. 已选企业状态：项目区域应展示
  await page.evaluate(() => {
    localStorage.setItem(
      'bidcraft-ui',
      JSON.stringify({
        state: {
          themeMode: 'light',
          currentEnterprise: { id: 'ent-1', name: '测试企业', agent: '张三' },
          currentProject: null,
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
  await page.screenshot({ path: 'screenshot-twostep-with-ent.png', fullPage: true })
  console.log('2. with-ent screenshot saved')

  await browser.close()
  console.log('OK: two-step screenshots saved')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
