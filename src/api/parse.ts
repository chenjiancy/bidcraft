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

export interface ExtractionSummary {
  doc_type: string | null
  items_total: number
  items_extracted: number
  red_flags: number
  llm: Record<string, unknown> | null
}

export interface ScoreSummary {
  categories: number
  total_score: number | null
  score_ok: boolean | null
  red_flags: number
  schema_validated: boolean | null
  llm: Record<string, unknown> | null
}

export interface DocxSummary {
  sources: number
  files: number
  cover: boolean
  completed: boolean | null
  errors: number
  red_flags: number
  missing_format_sources: string[]
}

export interface ConfirmedSummary {
  confirmed_at: string | null
  total_items: number
  confirmed_items: number
  all_confirmed: boolean
}

export interface ParseStatus {
  parse_status: string
  running: boolean
  sources: Record<string, unknown>
  checkpoint: CheckpointSummary | null
  chapters: Record<string, unknown> | null
  dedupe: Record<string, unknown> | null
  extraction: ExtractionSummary | null
  score: ScoreSummary | null
  docx: DocxSummary | null
  confirmed: ConfirmedSummary | null
}

// ---------- Task 13：解析清单复核与确认 ----------

export interface ExtractMatch {
  source: string
  chapter_path: string | null
  heading: string | null
  anchor: string | null
  snippet: string | null
  anchor_verified: boolean | null
  constraints: string | null
}

export interface ExtractItem {
  key: string
  label: string
  category: string
  selected: boolean
  status: string | null
  matches: ExtractMatch[]
}

export interface ExtractList {
  version: number
  rules_version: string
  generated_at: string
  doc_type: Record<string, unknown> | null
  items: ExtractItem[]
  sections_nature: Record<string, unknown> | null
  red_flags: Array<Record<string, unknown>>
  llm: Record<string, unknown> | null
}

export interface ScoreItem {
  name: string
  score: number | null
  materials: string[]
  thresholds: unknown[]
  line: number | null
}

export interface ScoreCategory {
  name: string
  source_chapter: string | null
  source_stem: string | null
  page_idx: number | null
  items: ScoreItem[]
}

export interface ScoreTable {
  generated_at: string
  categories: ScoreCategory[]
  total_score_check: { expected: number | null; actual: number | null; ok: boolean }
  red_flags: Array<Record<string, unknown>>
  schema_validated: boolean
  llm: Record<string, unknown> | null
}

export interface DocxFile {
  source_stem: string
  seq: number
  title: string
  kind: string
  file: string
  start_page: number | null
  end_page: number | null
  state: string
  error: string | null
  red_flags: number
  checkpoint_key: string
}

export interface DocxManifest {
  generated_at: string
  completed: boolean
  total_files: number
  sources: Array<{
    source_stem: string
    found: boolean
    cover: boolean
    note: string | null
    sections: Array<Record<string, unknown>>
    files: DocxFile[]
  }>
}

export interface ParseChecklist {
  parse_status: string
  extraction: ExtractList | null
  score: ScoreTable | null
  docx: DocxManifest | null
  confirmed: Record<string, unknown> | null
  review_state: ConfirmedSummary | null
}

export interface ParseConfirmItem {
  tab: 'extraction' | 'score' | 'docx'
  item_id: string
  confirmed: boolean
  override?: Record<string, unknown>
  deleted?: boolean
}

export interface ParseConfirmPayload {
  items: ParseConfirmItem[]
  extraction?: ExtractList
  score?: ScoreTable
  docx?: DocxManifest
  note?: string
}

export interface ParseConfirmResult {
  parse_status: string
  confirmed_at: string
  checklist_path: string
  total_items: number
  confirmed_items: number
}

export interface FormatListItem {
  key: string
  seq: number
  title: string
  file: string
  is_external: boolean
  source_stem: string
  status: 'confirmed' | 'missing' | 'added' | 'removed'
  missing_reason: string | null
  added_file: string | null
}

export interface FormatListData {
  parse_status: string
  items: FormatListItem[]
  confirmed_at: string | null
  total: number
  confirmed_count: number
  missing_count: number
  external_count: number
}

// ---------- Task 14：商务标格式清单确认 ----------

export function enterFormatReview(
  enterpriseId: string,
  projectId: string,
): Promise<{ parse_status: string; review_started_at: string }> {
  return window.bid.sidecar.call(
    projectRoute(enterpriseId, projectId, 'format/review'),
    {},
  ) as Promise<{
    parse_status: string
    review_started_at: string
  }>
}

export function getFormatList(enterpriseId: string, projectId: string): Promise<FormatListData> {
  return window.bid.sidecar.call(
    projectRoute(enterpriseId, projectId, 'format/list'),
  ) as Promise<FormatListData>
}

export function addFormatItemPath(
  enterpriseId: string,
  projectId: string,
  filePath: string,
  title: string | null,
): Promise<{ key: string; file: string }> {
  return window.bid.sidecar.call(projectRoute(enterpriseId, projectId, 'format/add_path'), {
    file_path: filePath,
    title,
  }) as Promise<{ key: string; file: string }>
}

export function addFormatItemName(
  enterpriseId: string,
  projectId: string,
  name: string,
): Promise<{ key: string; status: string }> {
  return window.bid.sidecar.call(projectRoute(enterpriseId, projectId, 'format/add_name'), {
    name,
  }) as Promise<{ key: string; status: string }>
}

export function removeFormatItem(
  enterpriseId: string,
  projectId: string,
  itemKey: string,
): Promise<{ removed: string }> {
  return window.bid.sidecar.call(
    `${projectRoute(enterpriseId, projectId, 'format/remove')}?item_key=${encodeURIComponent(itemKey)}`,
  ) as Promise<{ removed: string }>
}

export function updateFormatItem(
  enterpriseId: string,
  projectId: string,
  itemKey: string,
  title: string | null,
  file: string | null,
): Promise<{ updated: string }> {
  return window.bid.sidecar.call(
    `${projectRoute(enterpriseId, projectId, 'format/update')}?item_key=${encodeURIComponent(itemKey)}`,
    { title, file },
  ) as Promise<{ updated: string }>
}

export function confirmFormatList(
  enterpriseId: string,
  projectId: string,
  items: Array<{ key: string; confirmed: boolean }>,
  note?: string | null,
): Promise<{
  parse_status: string
  confirmed_at: string
  total_items: number
  confirmed_items: number
}> {
  return window.bid.sidecar.call(projectRoute(enterpriseId, projectId, 'format/confirm'), {
    items,
    note: note ?? null,
  }) as Promise<{
    parse_status: string
    confirmed_at: string
    total_items: number
    confirmed_items: number
  }>
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
 * apiKey：LLM 校验模式所需（DPAPI 取出后临时透传，不落库）。
 * @returns 终态事件（completed/failed/cancelled）
 */
export function startParse(
  enterpriseId: string,
  projectId: string,
  reparse: boolean,
  onProgress: (event: ParseEvent) => void,
  apiKey?: string | null,
): Promise<ParseEvent> {
  return window.bid.sidecar.stream(
    projectRoute(enterpriseId, projectId, 'start'),
    { reparse, api_key: apiKey ?? null },
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

// ---------- Task 13：解析清单复核与确认 ----------

export function getParseChecklist(
  enterpriseId: string,
  projectId: string,
): Promise<ParseChecklist> {
  return window.bid.sidecar.call(
    projectRoute(enterpriseId, projectId, 'checklist'),
  ) as Promise<ParseChecklist>
}

export function enterParseReview(
  enterpriseId: string,
  projectId: string,
): Promise<{ parse_status: string; review_started_at: string }> {
  return window.bid.sidecar.call(projectRoute(enterpriseId, projectId, 'review'), {}) as Promise<{
    parse_status: string
    review_started_at: string
  }>
}

export function confirmParseChecklist(
  enterpriseId: string,
  projectId: string,
  payload: ParseConfirmPayload,
): Promise<ParseConfirmResult> {
  return window.bid.sidecar.call(
    projectRoute(enterpriseId, projectId, 'confirm'),
    payload,
  ) as Promise<ParseConfirmResult>
}
