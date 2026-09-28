// 重置开发环境：删除 %AppData%\BidCraft-dev（architecture.md 10.6）
const { rmSync, existsSync } = require('node:fs')
const { join } = require('node:path')

const target = join(process.env.APPDATA || '', 'BidCraft-dev')

if (!existsSync(target)) {
  console.log(`[reset:dev] 目录不存在，无需清理：${target}`)
  process.exit(0)
}

rmSync(target, { recursive: true, force: true })
console.log(`[reset:dev] 已删除：${target}`)
