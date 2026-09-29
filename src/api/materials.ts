/** 素材库 API 封装（Task 15）。 */

const BASE = '/api/v1'

export interface Material {
  id: string
  enterprise_id: string
  project_id: string | null
  category: string
  name: string
  filename: string
  file_path: string
  ocr_text: string | null
  valid_until: string | null
  version: number
  status: string
  created_at: string
  updated_at: string
}

export interface MaterialList {
  items: Material[]
  total: number
}

export interface MaterialCreateIn {
  name?: string
  category: string
  filename?: string
  valid_until?: string | null
  fields?: Record<string, string> | null
}

export interface MaterialUpdateIn {
  name?: string
  filename?: string
  ocr_text?: string | null
  valid_until?: string | null
}

export interface MaterialPathIn {
  file_paths: string[]
  category: string
  name?: string
  filename?: string
  valid_until?: string | null
  fields?: Record<string, string> | null
}

async function call<T>(route: string, payload?: unknown, method?: string): Promise<T> {
  return window.bid.sidecar.call(route, payload, method) as Promise<T>
}

// ========== 企业共享素材 ==========

export function listMaterials(
  enterpriseId: string,
  options?: { category?: string; keyword?: string; page?: number; page_size?: number },
): Promise<MaterialList> {
  const params = new URLSearchParams()
  if (options?.category) params.set('category', options.category)
  if (options?.keyword) params.set('keyword', options.keyword)
  if (options?.page) params.set('page', String(options.page))
  if (options?.page_size) params.set('page_size', String(options.page_size))
  const query = params.toString() ? `?${params}` : ''
  return call<MaterialList>(`${BASE}/enterprises/${enterpriseId}/materials${query}`)
}

export function getMaterial(enterpriseId: string, materialId: string): Promise<Material> {
  return call<Material>(`${BASE}/enterprises/${enterpriseId}/materials/${materialId}`)
}

export function createMaterialFromPath(
  enterpriseId: string,
  data: MaterialPathIn,
): Promise<Material[]> {
  return call<Material[]>(`${BASE}/enterprises/${enterpriseId}/materials/from_path`, data)
}

export function updateMaterial(
  enterpriseId: string,
  materialId: string,
  data: MaterialUpdateIn,
): Promise<Material> {
  return call<Material>(`${BASE}/enterprises/${enterpriseId}/materials/${materialId}`, data, 'PUT')
}

export function deleteMaterial(
  enterpriseId: string,
  materialId: string,
): Promise<{ deleted: string }> {
  return call<{ deleted: string }>(
    `${BASE}/enterprises/${enterpriseId}/materials/${materialId}`,
    undefined,
    'DELETE',
  )
}

// ========== 项目独享素材 ==========

export function listProjectMaterials(
  enterpriseId: string,
  projectId: string,
  options?: { category?: string; keyword?: string; page?: number; page_size?: number },
): Promise<MaterialList> {
  const params = new URLSearchParams()
  if (options?.category) params.set('category', options.category)
  if (options?.keyword) params.set('keyword', options.keyword)
  if (options?.page) params.set('page', String(options.page))
  if (options?.page_size) params.set('page_size', String(options.page_size))
  const query = params.toString() ? `?${params}` : ''
  return call<MaterialList>(
    `${BASE}/enterprises/${enterpriseId}/projects/${projectId}/materials${query}`,
  )
}

export function createProjectMaterialFromPath(
  enterpriseId: string,
  projectId: string,
  data: MaterialPathIn,
): Promise<Material[]> {
  return call<Material[]>(
    `${BASE}/enterprises/${enterpriseId}/projects/${projectId}/materials/from_path`,
    data,
  )
}
