/**
 * 招标文件解析 API（Task 8）。
 * 登记/启动(SSE)/状态/单项重试/取消，经 Electron IPC 转发到同机 sidecar。
 */

const BASE = '/api/v1'

export interface LocalSourceFile {
  /** 文件对话框返回的文件名（含扩展名） */
  name: string
  /** 本机绝对路径，sidecar 复制入库 */
  path: string
}

export interface EngineStatus {
  available: boolean
  python_path: string | null
  version: string | null
  cuda_available: boolean | null
  cuda_device: string | null
  error: string | null
  libreoffice_available: boolean
}

/** SSE 进度事件，形态与 electron/lib/sse.ts 一致 */
export interface ParseEvent {
  stage: string
  percent: number
  message: string
  extra?: Record<string, unknown>
}

export type CheckpointItemState = 'idle' | 'running' | 'success' | 'error'

export interface CheckpointItem {
  key: string
  label: string
  state: CheckpointItemState
  attempts: number
  error: string | null
  updated_at?: string
}

export interface CheckpointSummary {
  job_type: string
  state: string
  counts: Partial<Record<CheckpointItemState, number>>
  updated_at: string
  items: CheckpointItem[]
}

export interface ParseStatus {
  parse_status: string
  running: boolean
  sources: Record<string, unknown>
  checkpoint: CheckpointSummary | null
  chapters: Record<string, unknown> | null
  dedupe: Record<string, unknown> | null
}

// ---------- Task 9：解析配置 ----------

export interface ParseConfigItem {
  key: string
  label: string
  required: boolean
  selected: boolean
}

/** LLM 辅助模式：校验 / 双通道（双通道后续迭代落地，当前仅存储选择） */
export type LlmMode = 'validate' | 'dual_channel'

export interface ParseConfig {
  /** true = 项目从未保存过配置，返回的是默认配置 */
  is_default: boolean
  items: ParseConfigItem[]
  llm_enabled: boolean
  llm_mode: LlmMode | string
}

export interface ParseConfigSaveResult {
  config: ParseConfig
  /** PARSED 后发生配置变更：要素层需重新解析才生效 */
  reparse_required: boolean
  changes: Record<string, unknown>
  /** 受影响 checkpoint item keys（Task 9 恒空，Task 10 扩展单项重试） */
  affected_items: string[]
}

function projectRoute(enterpriseId: string, projectId: string, action: string): string {
  return `${BASE}/enterprises/${enterpriseId}/projects/${projectId}/parse/${action}`
}

export function getEngineStatus(): Promise<EngineStatus> {
  return window.bid.sidecar.call(`${BASE}/parse/engine`) as Promise<EngineStatus>
}

export function registerSources(
  enterpriseId: string,
  projectId: string,
  files: LocalSourceFile[],
): Promise<unknown> {
  return window.bid.sidecar.call(projectRoute(enterpriseId, projectId, 'sources'), { files })
}

/**
 * 启动解析（或断点续跑），订阅 SSE 进度。
 * onProgress 会先收到一条 stage='meta' 事件，extra.taskId 可用于取消。
 * @returns 终态事件（completed/failed/cancelled）
 */
export function startParse(
  enterpriseId: string,
  projectId: string,
  reparse: boolean,
  onProgress: (event: ParseEvent) => void,
): Promise<ParseEvent> {
  return window.bid.sidecar.stream(
    projectRoute(enterpriseId, projectId, 'start'),
    { reparse },
    onProgress,
  ) as Promise<ParseEvent>
}

export function getParseStatus(enterpriseId: string, projectId: string): Promise<ParseStatus> {
  return window.bid.sidecar.call(
    projectRoute(enterpriseId, projectId, 'status'),
  ) as Promise<ParseStatus>
}

/** 单项重试；item 为 null 时整任务续跑（只跑未成功项） */
export function retryParseItem(
  enterpriseId: string,
  projectId: string,
  item: string | null,
): Promise<unknown> {
  return window.bid.sidecar.call(projectRoute(enterpriseId, projectId, 'retry'), { item })
}

export function cancelParseTask(taskId: string): Promise<unknown> {
  return window.bid.sidecar.cancelTask(taskId)
}

export function getParseConfig(enterpriseId: string, projectId: string): Promise<ParseConfig> {
  return window.bid.sidecar.call(
    projectRoute(enterpriseId, projectId, 'config'),
  ) as Promise<ParseConfig>
}

export function updateParseConfig(
  enterpriseId: string,
  projectId: string,
  selected: string[],
  llmEnabled: boolean,
  llmMode: LlmMode,
): Promise<ParseConfigSaveResult> {
  return window.bid.sidecar.call(
    projectRoute(enterpriseId, projectId, 'config'),
    { selected, llm_enabled: llmEnabled, llm_mode: llmMode },
    'PUT',
  ) as Promise<ParseConfigSaveResult>
}
