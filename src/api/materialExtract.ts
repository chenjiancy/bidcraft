/** 素材提取清单 API 封装（Task 16）。 */

const BASE = '/api/v1'

export interface ExtractItem {
  id: string
  requirement_name: string
  source: string
  source_anchor: string | null
  selected_material_id: string | null
  status: string
  confirmed_at: string | null
  round: number
}

export interface ExtractList {
  items: ExtractItem[]
  total: number
  pending: number
  selected: number
  missing: number
}

export interface CandidateItem {
  id: string
  name: string
  filename: string
  file_path: string
  category: string
  valid_until: string | null
  rank: number
}

export interface CandidateGroup {
  group_key: string
  items: CandidateItem[]
}

export interface ExtractQueryOut {
  candidates: CandidateGroup[]
  total: number
}

export interface SaveRoundChange {
  item_id: string
  status?: string
  selected_material_id?: string
}

async function call<T>(route: string, payload?: unknown, method?: string): Promise<T> {
  return window.bid.sidecar.call(route, payload, method) as Promise<T>
}

function base(eid: string, pid: string): string {
  return `${BASE}/enterprises/${eid}/projects/${pid}/material-extract`
}

export function getExtractList(eid: string, pid: string, round?: number): Promise<ExtractList> {
  const q = round != null ? `?round=${round}` : ''
  return call<ExtractList>(`${base(eid, pid)}${q}`)
}

export function generateExtractList(
  eid: string,
  pid: string,
  round = 1,
): Promise<{ requirement_count: number; round: number; items: ExtractItem[] }> {
  return call(`${base(eid, pid)}/generate?round=${round}`, undefined, 'POST')
}

export function queryCandidates(
  eid: string,
  pid: string,
  body: { requirement_name?: string; keyword?: string },
): Promise<ExtractQueryOut> {
  return call<ExtractQueryOut>(`${base(eid, pid)}/query`, body, 'POST')
}

export function addRequirement(
  eid: string,
  pid: string,
  body: { requirement_name: string; source?: string; source_anchor?: string },
): Promise<ExtractItem> {
  return call<ExtractItem>(`${base(eid, pid)}/items`, body, 'POST')
}

export function updateRequirement(
  eid: string,
  pid: string,
  itemId: string,
  body: { requirement_name: string },
): Promise<ExtractItem> {
  return call<ExtractItem>(`${base(eid, pid)}/items/${itemId}`, body, 'PUT')
}

export function deleteRequirement(
  eid: string,
  pid: string,
  itemId: string,
): Promise<{ deleted: string }> {
  return call(`${base(eid, pid)}/items/${itemId}`, undefined, 'DELETE')
}

export function saveRound(
  eid: string,
  pid: string,
  body: { round: number; changes: SaveRoundChange[] },
): Promise<ExtractList> {
  return call<ExtractList>(`${base(eid, pid)}/save-round`, body, 'POST')
}

export function startNewRound(
  eid: string,
  pid: string,
): Promise<{ round: number; item_count: number }> {
  return call(`${base(eid, pid)}/new-round`, undefined, 'POST')
}

export function importExternal(
  eid: string,
  pid: string,
  body: { file_path: string; category: string; name?: string },
): Promise<{ id: string; file_path: string }> {
  return call(`${base(eid, pid)}/import-external`, body, 'POST')
}

export function confirmExtractList(
  eid: string,
  pid: string,
  round?: number,
): Promise<{ confirmed_at: string; round: number; item_count: number }> {
  const q = round != null ? `?round=${round}` : ''
  return call(`${base(eid, pid)}/confirm${q}`, undefined, 'POST')
}
