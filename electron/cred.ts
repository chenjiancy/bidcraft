/**
 * DPAPI 凭据管理（NFR-3 / architecture.md 第八章）。
 *
 * 使用 Windows DPAPI（经 PowerShell ConvertTo/From-SecureString）加密 API Key，
 * 密文存储在 userData/cred.json 中。
 * - 加密后只有当前 Windows 用户可解密
 * - API Key 不落 sidecar 数据库、不落日志
 */

import { execFile } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { app, ipcMain } from 'electron'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)

const CRED_FILE = 'cred.json'

function credPath(): string {
  const dir = app.getPath('userData')
  return join(dir, CRED_FILE)
}

interface CredData {
  encrypted_api_key: string | null
}

function readCred(): CredData {
  const path = credPath()
  if (!existsSync(path)) return { encrypted_api_key: null }
  try {
    return JSON.parse(readFileSync(path, 'utf-8')) as CredData
  } catch {
    return { encrypted_api_key: null }
  }
}

function writeCred(data: CredData): void {
  const dir = app.getPath('userData')
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  writeFileSync(credPath(), JSON.stringify(data, null, 2), 'utf-8')
}

async function dpapiEncrypt(plain: string): Promise<string> {
  const script = `
$ErrorActionPreference = 'Stop'
$s = ConvertTo-SecureString -String '${plain.replace(/'/g, "''")}' -AsPlainText -Force
ConvertFrom-SecureString $s | Out-File -FilePath '$env:TEMP\\dpapi_out.txt' -Encoding utf8 -NoNewline
`.trim()
  await execFileAsync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script])
  const os = await import('node:os')
  const tmpPath = join(os.tmpdir(), 'dpapi_out.txt')
  const encrypted = readFileSync(tmpPath, 'utf-8').trim()
  return encrypted
}

async function dpapiDecrypt(encrypted: string): Promise<string> {
  const script = `
$ErrorActionPreference = 'Stop'
$e = @'
${encrypted}
'@
$s = ConvertTo-SecureString -String $e.Trim()
[Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
`.trim()
  const { stdout } = await execFileAsync('powershell.exe', [
    '-NoProfile',
    '-NonInteractive',
    '-Command',
    script,
  ])
  return stdout.trim()
}

export async function setApiKey(apiKey: string): Promise<void> {
  const encrypted = await dpapiEncrypt(apiKey)
  writeCred({ encrypted_api_key: encrypted })
}

export async function getApiKey(): Promise<string | null> {
  const data = readCred()
  if (!data.encrypted_api_key) return null
  return dpapiDecrypt(data.encrypted_api_key)
}

export function hasApiKey(): boolean {
  return readCred().encrypted_api_key !== null
}

export function clearApiKey(): void {
  const path = credPath()
  if (existsSync(path)) unlinkSync(path)
}

/** 注册 cred IPC handlers */
export function registerCredIpc(): void {
  ipcMain.handle('cred:setApiKey', async (_event: unknown, apiKey: string) => {
    await setApiKey(apiKey)
    return { success: true }
  })
  ipcMain.handle('cred:getApiKey', async () => {
    return getApiKey()
  })
  ipcMain.handle('cred:hasApiKey', () => {
    return hasApiKey()
  })
  ipcMain.handle('cred:clearApiKey', () => {
    clearApiKey()
    return { success: true }
  })
}
