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
