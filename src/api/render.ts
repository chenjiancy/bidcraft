/** 渲染 API（Task 19）。 */

const BASE = '/api/v1'
const RENDER_PREFIX = 'render'

function route(enterpriseId: string, projectId: string, action: string): string {
  return `${BASE}/enterprises/${enterpriseId}/projects/${projectId}/${RENDER_PREFIX}/${action}`
}

// ---------- 类型定义 ----------

export interface PlaceholderInfo {
  name: string
  type: 'a_class' | 'b_class' | 'image'
  description: string
  value: string | null
  needs_manual: boolean
  is_missing: boolean
}

export interface RenderPlanItem {
  chapter: string
  seq: number
  template_path: string
  placeholders: PlaceholderInfo[]
  missing_count: number
}

export interface RenderPlan {
  plan: RenderPlanItem[]
  total: number
  missing_total: number
}

export interface BClassAdjustment {
  placeholder: string
  value: string
}

export interface ConfirmPlanResult {
  status: string
  total_placeholders: number
  b_class_needs_manual: number
  missing_count: number
}

export interface RenderProgressEvent {
  type: 'progress' | 'error'
  event?: string
  message?: string
  paths?: string[]
}

export interface WarningItem {
  chapter: string
  placeholder: string
  problem_type: 'missing_text' | 'missing_image' | 'b_class_uncertain'
  suggestion: string
}

export interface WarningList {
  warnings: WarningItem[]
  total: number
  missing_text: number
  missing_image: number
  b_class_uncertain: number
}

export interface TermIssue {
  chapter: string
  term: string
  count: number
  expected: string
}

export interface ConsistencyIssue {
  field: string
  description: string
  chapters: Record<string, string>
  problem: string
}

export interface AuditResult {
  doc_type: string
  term_issues: TermIssue[]
  consistency_issues: ConsistencyIssue[]
  summary: string
}

export interface RenderStatus {
  parse_status: string
  rendering: boolean
  current_chapter: string | null
  completed_chapters: string[]
  total_chapters: number
  error_msg: string | null
}

// ---------- API 函数 ----------

export function getRenderPlan(enterpriseId: string, projectId: string): Promise<RenderPlan> {
  return window.bid.sidecar.call(route(enterpriseId, projectId, 'plan')) as Promise<RenderPlan>
}

export function confirmRenderPlan(
  enterpriseId: string,
  projectId: string,
  adjustments: BClassAdjustment[],
  note?: string | null,
): Promise<ConfirmPlanResult> {
  return window.bid.sidecar.call(route(enterpriseId, projectId, 'confirm'), {
    b_class_adjustments: adjustments,
    note: note ?? null,
  }) as Promise<ConfirmPlanResult>
}

/**
 * 启动渲染（SSE）。
 * @returns 终态事件（completed/cancelled/error）
 */
export function startRender(
  enterpriseId: string,
  projectId: string,
  onProgress: (event: RenderProgressEvent) => void,
): Promise<RenderProgressEvent> {
  return window.bid.sidecar.stream(
    route(enterpriseId, projectId, 'start'),
    { re_render: false },
    onProgress,
  ) as Promise<RenderProgressEvent>
}

export function cancelRender(
  enterpriseId: string,
  projectId: string,
): Promise<{ cancelled: boolean }> {
  return window.bid.sidecar.call(route(enterpriseId, projectId, 'cancel'), {}) as Promise<{
    cancelled: boolean
  }>
}

export function getRenderStatus(enterpriseId: string, projectId: string): Promise<RenderStatus> {
  return window.bid.sidecar.call(route(enterpriseId, projectId, 'status')) as Promise<RenderStatus>
}

export function retryRenderChapter(
  enterpriseId: string,
  projectId: string,
  chapter: string,
): Promise<{ chapter: string; output_path: string; re_rendered: boolean }> {
  return window.bid.sidecar.call(
    route(enterpriseId, projectId, `retry?chapter=${encodeURIComponent(chapter)}`),
    {},
  ) as Promise<{ chapter: string; output_path: string; re_rendered: boolean }>
}

export function getWarnings(enterpriseId: string, projectId: string): Promise<WarningList> {
  return window.bid.sidecar.call(route(enterpriseId, projectId, 'warnings')) as Promise<WarningList>
}

export function getAuditResult(enterpriseId: string, projectId: string): Promise<AuditResult> {
  return window.bid.sidecar.call(route(enterpriseId, projectId, 'audit')) as Promise<AuditResult>
}

export function downloadChapter(enterpriseId: string, projectId: string, chapter: string): string {
  // 直接返回浏览器可访问的下载 URL（sidecar 支持文件流）
  return route(enterpriseId, projectId, `download/${encodeURIComponent(chapter)}`)
}
