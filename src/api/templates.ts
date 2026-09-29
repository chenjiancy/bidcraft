/** 模板库 API 封装（Task 17）。 */

const BASE = '/api/v1'

export interface TemplateOut {
  id: string
  enterprise_id: string
  agency: string
  doc_type: string
  name: string
  version: number
  path: string
  meta: {
    chapters: string[]
    note: string
    change_note?: string
    image_max_width_cm?: number
    image_max_height_cm?: number
    created_at: string
  }
  status: string
  referenced: boolean
  created_at: string
  updated_at: string
}

export interface TemplateList {
  items: TemplateOut[]
  total: number
}

export interface TemplateCreateIn {
  agency: string
  doc_type: 'bid' | 'procurement' | 'quotation'
  name: string
  file_paths: string[]
  image_max_width_cm?: number | null
  image_max_height_cm?: number | null
  note: string
}

export interface TemplateNewVersionIn {
  file_paths: string[]
  change_note: string
  image_max_width_cm?: number | null
  image_max_height_cm?: number | null
  note: string
}

export interface TemplateUpdateIn {
  agency?: string
  doc_type?: string
  name?: string
  image_max_width_cm?: number | null
  image_max_height_cm?: number | null
  note?: string
}

export interface ComplianceIssue {
  code: string
  message: string
  file: string | null
}

export interface ComplianceResult {
  ok: boolean
  issues: ComplianceIssue[]
  placeholders: Array<{ placeholder: string; kind: string }>
}

async function call<T>(route: string, payload?: unknown, method?: string): Promise<T> {
  return window.bid.sidecar.call(route, payload, method) as Promise<T>
}

// ========== 企业共享模板库 ==========

export function listTemplates(
  enterpriseId: string,
  options?: { agency?: string; doc_type?: string; name?: string },
): Promise<TemplateList> {
  const params = new URLSearchParams()
  if (options?.agency) params.set('agency', options.agency)
  if (options?.doc_type) params.set('doc_type', options.doc_type)
  if (options?.name) params.set('name', options.name)
  const query = params.toString() ? `?${params}` : ''
  return call<TemplateList>(`${BASE}/enterprises/${enterpriseId}/templates${query}`)
}

export function getTemplate(enterpriseId: string, templateId: string): Promise<TemplateOut> {
  return call<TemplateOut>(`${BASE}/enterprises/${enterpriseId}/templates/${templateId}`)
}

export function createTemplateFromPath(
  enterpriseId: string,
  data: TemplateCreateIn,
): Promise<TemplateOut> {
  return call<TemplateOut>(`${BASE}/enterprises/${enterpriseId}/templates/from_path`, data)
}

export function updateTemplate(
  enterpriseId: string,
  templateId: string,
  data: TemplateUpdateIn,
): Promise<TemplateOut> {
  return call<TemplateOut>(
    `${BASE}/enterprises/${enterpriseId}/templates/${templateId}`,
    data,
    'PUT',
  )
}

export function deleteTemplate(
  enterpriseId: string,
  templateId: string,
): Promise<{ deleted: string }> {
  return call<{ deleted: string }>(
    `${BASE}/enterprises/${enterpriseId}/templates/${templateId}`,
    undefined,
    'DELETE',
  )
}

export function newVersion(
  enterpriseId: string,
  templateId: string,
  data: TemplateNewVersionIn,
): Promise<TemplateOut> {
  return call<TemplateOut>(
    `${BASE}/enterprises/${enterpriseId}/templates/${templateId}/new-version`,
    data,
  )
}

export function overwriteLatest(
  enterpriseId: string,
  templateId: string,
  data: TemplateNewVersionIn,
): Promise<TemplateOut> {
  return call<TemplateOut>(
    `${BASE}/enterprises/${enterpriseId}/templates/${templateId}/overwrite`,
    data,
  )
}

export function checkCompliance(
  enterpriseId: string,
  templateId: string,
  data: TemplateNewVersionIn,
): Promise<ComplianceResult> {
  return call<ComplianceResult>(
    `${BASE}/enterprises/${enterpriseId}/templates/${templateId}/compliance`,
    data,
  )
}

export function registerPlaceholders(
  enterpriseId: string,
  placeholders: string[],
): Promise<{ added: number }> {
  return call<{ added: number }>(`${BASE}/enterprises/${enterpriseId}/templates/dict-register`, {
    placeholders,
  })
}

export function checkExternalWrite(
  enterpriseId: string,
): Promise<{ modified: string[]; count: number }> {
  return call<{ modified: string[]; count: number }>(
    `${BASE}/enterprises/${enterpriseId}/templates/check-external-write`,
  )
}
