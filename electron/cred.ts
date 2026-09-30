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

/**
 * 使用 -EncodedCommand 执行加密脚本，避免 Out-File 的编码问题和临时文件竞争。
 *
 * 原来的 Out-File 方案在部分 Windows 环境下会因 UTF-8 BOM、临时目录权限
 * 或 PowerShell 输出编码导致密文为空，进而让 hasApiKey() 返回 false。
 * -EncodedCommand 直接返回 Base64 密文到 stdout，不依赖文件系统。
 */
async function dpapiEncrypt(plain: string): Promise<string> {
  const escaped = plain.replace(/'/g, "''")
  const script = `$s = ConvertTo-SecureString -String '${escaped}' -AsPlainText -Force; ConvertFrom-SecureString $s`
  // ucs2 编码（UTF-16LE）是 PowerShell -EncodedCommand 的固定要求
  const bytes = Buffer.from(script, 'ucs2')
  const encoded = bytes.toString('base64')
  const { stdout } = await execFileAsync('powershell.exe', [
    '-NoProfile',
    '-NonInteractive',
    '-EncodedCommand',
    encoded,
  ])
  const encrypted = stdout.trim()
  if (!encrypted) throw new Error('DPAPI 加密失败：PowerShell 未返回密文')
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
