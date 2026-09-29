/** 模板匹配与语义比对 API 封装（Task 18）。 */

const BASE = '/api/v1'

export interface SimilarityComponent {
  score: number
  [key: string]: unknown
}

export interface MatchCandidate {
  score: number
  chapter_match_rate?: number
  count_score?: number
  order_score?: number
  agency_score?: number
  doc_type_score?: number
  template_id: string
  template_name: string
  agency: string
  doc_type: string
  version: number
  components?: SimilarityComponent[]
  details?: Record<string, unknown>
}

export interface AutoMatchResult {
  best_match: MatchCandidate | null
  candidates: MatchCandidate[]
  has_match: boolean
  threshold: number
  error?: string | null
}

export interface AssociationRow {
  parsed_key: string
  template_stem: string | null
  method?: string
  [key: string]: unknown
}

export interface Finding {
  id: string
  chapter_key: string
  finding_type: string
  diff_summary: string
  parsed_anchor: string | null
  template_content: string
  confidence: 'high' | 'low' | string
  suggested_action: string
  is_mechanical_red_flag: boolean
  requires_disclosure: boolean
  resolved_action?: string | null
  resolved_note?: string | null
  resolved_at?: string | null
}

export interface CompareStatus {
  parse_status: string
  has_compare: boolean
  compare_id?: string
  status?: string | null
  match_method?: string | null
  similarity_score?: number | null
  work_dir?: string | null
  findings_count: number
  accepted_count: number
  rejected_count: number
  ready_at?: string | null
  findings?: Finding[]
  association?: AssociationRow[] | Record<string, unknown>
}

export interface RunCompareResult {
  compare_id: string
  findings_count: number
  unmatched_count: number
  findings: Finding[]
  associations: AssociationRow[]
  schema_valid: boolean
  schema_errors: string[]
}

export interface CopiedFile {
  template_id: string
  name: string
  version: number
  files: string[]
  [key: string]: unknown
}

async function call<T>(route: string, payload?: unknown, method?: string): Promise<T> {
  return window.bid.sidecar.call(route, payload, method) as Promise<T>
}

function base(eid: string, pid: string): string {
  return `${BASE}/enterprises/${eid}/projects/${pid}/template-match`
}

export function getTemplateMatchStatus(eid: string, pid: string): Promise<CompareStatus> {
  return call<CompareStatus>(`${base(eid, pid)}/status`)
}

export function enterTemplateMatching(
  eid: string,
  pid: string,
): Promise<{ parse_status: string; work_dir: string }> {
  return call(`${base(eid, pid)}/enter`, undefined, 'POST')
}

export function autoMatchTemplates(eid: string, pid: string): Promise<AutoMatchResult> {
  return call<AutoMatchResult>(`${base(eid, pid)}/auto-match`)
}

export function copyTemplatesToWork(
  eid: string,
  pid: string,
  templateIds: string[],
): Promise<{ work_dir: string; copied: CopiedFile[] }> {
  return call(`${base(eid, pid)}/copy`, { template_ids: templateIds }, 'POST')
}

export function runTemplateCompare(eid: string, pid: string): Promise<RunCompareResult> {
  return call<RunCompareResult>(`${base(eid, pid)}/run-compare`, undefined, 'POST')
}

export function resolveFinding(
  eid: string,
  pid: string,
  findingId: string,
  action: 'update' | 'replace' | 'manual_review' | 'keep',
  note?: string | null,
): Promise<{ updated: string; action: string }> {
  return call(
    `${base(eid, pid)}/findings/${findingId}/resolve`,
    { finding_id: findingId, action, note: note ?? null },
    'POST',
  )
}

export function batchConfirmFindings(
  eid: string,
  pid: string,
  findingIds: string[],
  action: 'update' | 'replace' | 'keep',
  note?: string | null,
): Promise<{ confirmed_count: number; total_findings: number }> {
  return call(
    `${base(eid, pid)}/batch-confirm`,
    { finding_ids: findingIds, action, note: note ?? null },
    'POST',
  )
}

export function enterTemplateReview(
  eid: string,
  pid: string,
): Promise<{ parse_status: string; compare_id: string | null }> {
  return call(`${base(eid, pid)}/review`, undefined, 'POST')
}

export function confirmTemplateReview(eid: string, pid: string): Promise<{ parse_status: string }> {
  return call(`${base(eid, pid)}/confirm`, undefined, 'POST')
}

export function invalidateTemplateCompare(
  eid: string,
  pid: string,
): Promise<{ invalidated: boolean }> {
  return call(`${base(eid, pid)}/invalidate`, undefined, 'POST')
}
