// lint-staged 专用：接收暂存的 .py 文件路径（根目录相对路径），
// 剥离 sidecar/ 前缀后在 sidecar 目录内执行 ruff。
import { spawnSync } from 'node:child_process'

const files = process.argv
  .slice(2)
  .map((f) => f.replace(/^sidecar[\\/]/, ''))
  .filter(Boolean)

if (files.length === 0) process.exit(0)

const isWin = process.platform === 'win32'

const run = (args) =>
  spawnSync('uv', ['run', 'ruff', ...args], {
    cwd: 'sidecar',
    stdio: 'inherit',
    shell: isWin,
  })

const check = run(['check', '--fix', ...files])
if (check.status !== 0) process.exit(check.status ?? 1)

const format = run(['format', ...files])
if (format.status !== 0) process.exit(format.status ?? 1)
