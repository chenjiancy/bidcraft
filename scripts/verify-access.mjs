// 验证 access 统一管理：直接访问被锁定的路由应被拦截
// 用法: node scripts/verify-access.mjs
import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })

  // 已选项目但未确认解析，直接访问 /bid 应被拦截
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
  await page.goto(BASE + '/#/bid')
  await page.waitForTimeout(1500)
  await page.screenshot({ path: 'screenshot-access-blocked.png', fullPage: true })
  console.log('1. access-blocked screenshot saved')

  // 已确认解析后 /bid 可正常进入
  await page.evaluate(() => {
    localStorage.setItem(
      'bidcraft-ui',
      JSON.stringify({
        state: {
          themeMode: 'light',
          currentEnterprise: { id: 'ent-1', name: '测试企业', agent: '张三' },
          currentProject: { id: 'proj-1', name: '测试项目', agent: '张三' },
          isParseConfirmed: true,
          parseStatus: 'PARSE_CONFIRMED',
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
  await page.screenshot({ path: 'screenshot-access-allowed.png', fullPage: true })
  console.log('2. access-allowed screenshot saved')

  await browser.close()
  console.log('OK: access verification screenshots saved')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
