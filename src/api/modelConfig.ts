/** 模型配置 API 封装（经 IPC 转发到 sidecar；API Key 经 DPAPI 独立管理）。 */

const BASE = '/api/v1'

export interface ModelConfig {
  provider: string | null
  base_url: string | null
  model: string | null
}

export interface TestConnectionResult {
  success: boolean
  model: string
  response_text: string
  tokens_in: number | null
  tokens_out: number | null
  duration_ms: number
  error: string | null
}

export interface ModelConfigInput {
  provider: string
  base_url: string
  model: string
}

async function call<T>(route: string, payload?: unknown, method?: string): Promise<T> {
  return window.bid.sidecar.call(route, payload, method) as Promise<T>
}

// ========== 模型配置 CRUD ==========

export function getModelConfig(): Promise<ModelConfig> {
  return call<ModelConfig>(`${BASE}/model-config`)
}

export function updateModelConfig(data: ModelConfigInput): Promise<ModelConfig> {
  return call<ModelConfig>(`${BASE}/model-config`, data, 'PUT')
}

// ========== 测试连接 ==========

export async function testConnection(
  data: ModelConfigInput & { api_key: string },
): Promise<TestConnectionResult> {
  return call<TestConnectionResult>(`${BASE}/model-config/test`, data)
}

// ========== 首次外联确认（NFR-3） ==========

export function getExternalConfirmed(): Promise<{ confirmed: boolean }> {
  return call<{ confirmed: boolean }>(`${BASE}/model-config/external-confirmed`)
}

export function confirmExternal(): Promise<{ confirmed: boolean }> {
  return call<{ confirmed: boolean }>(`${BASE}/model-config/external-confirmed`, {})
}

// ========== API Key（DPAPI） ==========

export function setApiKey(apiKey: string): Promise<{ success: boolean }> {
  return window.bid.cred.setApiKey(apiKey)
}

export function getApiKey(): Promise<string | null> {
  return window.bid.cred.getApiKey()
}

export function hasApiKey(): Promise<boolean> {
  return window.bid.cred.hasApiKey()
}

export function clearApiKey(): Promise<{ success: boolean }> {
  return window.bid.cred.clearApiKey()
}
