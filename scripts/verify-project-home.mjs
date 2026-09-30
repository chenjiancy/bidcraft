// 验证项目首页模块卡片
// 用法: node scripts/verify-project-home.mjs
import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } })

  // 1. 已选项目但未确认解析：模块卡片应显示锁定状态
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
  await page.goto(BASE + '/#/project-home')
  await page.waitForTimeout(1500)
  await page.screenshot({ path: 'screenshot-home-locked.png', fullPage: true })
  console.log('1. locked screenshot saved')

  // 2. 已确认解析：商务标/素材提取/标书检查解锁
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
  await page.screenshot({ path: 'screenshot-home-parse-ok.png', fullPage: true })
  console.log('2. parse-ok screenshot saved')

  // 3. 已确认格式清单：全部解锁
  await page.evaluate(() => {
    localStorage.setItem(
      'bidcraft-ui',
      JSON.stringify({
        state: {
          themeMode: 'light',
          currentEnterprise: { id: 'ent-1', name: '测试企业', agent: '张三' },
          currentProject: { id: 'proj-1', name: '测试项目', agent: '张三' },
          isParseConfirmed: true,
          parseStatus: 'FORMAT_CONFIRMED',
          isFormatListConfirmed: true,
          formatStatus: 'FORMAT_CONFIRMED',
          materialStatus: undefined,
          isMaterialConfirmed: false,
        },
        version: 0,
      }),
    )
  })
  await page.reload()
  await page.waitForTimeout(1500)
  await page.screenshot({ path: 'screenshot-home-format-ok.png', fullPage: true })
  console.log('3. format-ok screenshot saved')

  // 4. 已确认素材：全部解锁
  await page.evaluate(() => {
    localStorage.setItem(
      'bidcraft-ui',
      JSON.stringify({
        state: {
          themeMode: 'light',
          currentEnterprise: { id: 'ent-1', name: '测试企业', agent: '张三' },
          currentProject: { id: 'proj-1', name: '测试项目', agent: '张三' },
          isParseConfirmed: true,
          parseStatus: 'MATERIAL_CONFIRMED',
          isFormatListConfirmed: true,
          formatStatus: 'MATERIAL_CONFIRMED',
          materialStatus: 'MATERIAL_CONFIRMED',
          isMaterialConfirmed: true,
        },
        version: 0,
      }),
    )
  })
  await page.reload()
  await page.waitForTimeout(1500)
  await page.screenshot({ path: 'screenshot-home-material-ok.png', fullPage: true })
  console.log('4. material-ok screenshot saved')

  await browser.close()
  console.log('OK: project-home screenshots saved')
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
