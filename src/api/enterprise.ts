/** 企业/项目/回收站 API 封装（经 IPC 转发到 sidecar）。 */

const BASE = '/api/v1'

export interface Enterprise {
  id: string
  name: string
  legal_person: string | null
  agent: string
  contact: string | null
  phone: string | null
  intro: string | null
  status: string
}

export interface Project {
  id: string
  enterprise_id: string
  name: string
  code: string | null
  agent: string
  status: string
  /** 解析状态机：INIT/UPLOADED/PARSING/PARSED */
  parse_status: string
}

export interface RecycleBinItem {
  id: string
  item_type: string
  enterprise_id: string | null
  ref_id: string
  deleted_at: string
  purge_at: string
}

export interface EnterpriseInput {
  name: string
  agent: string
  legal_person?: string
  contact?: string
  phone?: string
  intro?: string
}

export interface ProjectInput {
  name: string
  code?: string
  agent?: string
}

async function call<T>(route: string, payload?: unknown, method?: string): Promise<T> {
  return window.bid.sidecar.call(route, payload, method) as Promise<T>
}

// ========== 企业 ==========

export function listEnterprises(): Promise<Enterprise[]> {
  return call<Enterprise[]>(`${BASE}/enterprises`)
}

export function createEnterprise(data: EnterpriseInput): Promise<Enterprise> {
  return call<Enterprise>(`${BASE}/enterprises`, data)
}

export function getEnterprise(id: string): Promise<Enterprise> {
  return call<Enterprise>(`${BASE}/enterprises/${id}`)
}

export function updateEnterprise(
  id: string,
  data: Partial<Omit<EnterpriseInput, 'name' | 'agent'>> &
    Partial<Pick<EnterpriseInput, 'name' | 'agent'>>,
): Promise<Enterprise> {
  return call<Enterprise>(`${BASE}/enterprises/${id}`, data, 'PUT')
}

export function deleteEnterprise(id: string): Promise<void> {
  return call<void>(`${BASE}/enterprises/${id}`, undefined, 'DELETE')
}

// ========== 项目 ==========

export function listProjects(enterpriseId: string): Promise<Project[]> {
  return call<Project[]>(`${BASE}/enterprises/${enterpriseId}/projects`)
}

export function createProject(enterpriseId: string, data: ProjectInput): Promise<Project> {
  return call<Project>(`${BASE}/enterprises/${enterpriseId}/projects`, data)
}

export function updateProject(
  enterpriseId: string,
  projectId: string,
  data: Partial<ProjectInput>,
): Promise<Project> {
  return call<Project>(`${BASE}/enterprises/${enterpriseId}/projects/${projectId}`, data, 'PUT')
}

export function deleteProject(enterpriseId: string, projectId: string): Promise<void> {
  return call<void>(
    `${BASE}/enterprises/${enterpriseId}/projects/${projectId}`,
    undefined,
    'DELETE',
  )
}

// ========== 回收站 ==========

export function listRecycleBin(enterpriseId?: string): Promise<RecycleBinItem[]> {
  const query = enterpriseId ? `?enterprise_id=${enterpriseId}` : ''
  return call<RecycleBinItem[]>(`${BASE}/recycle-bin${query}`)
}

export function restoreItem(itemId: string): Promise<void> {
  return call<void>(`${BASE}/recycle-bin/${itemId}/restore`)
}

export function purgeItem(itemId: string): Promise<void> {
  return call<void>(`${BASE}/recycle-bin/${itemId}`, undefined, 'DELETE')
}
