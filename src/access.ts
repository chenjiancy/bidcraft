import { useAppStore } from './stores/useAppStore'

/**
 * 统一访问控制：路由与菜单共用同一套规则。
 *
 * access 字段说明：
 * - 'public'：无需登录/选择即可访问（如 /settings）
 * - 'enterprise'：需已选择企业
 * - 'project'：需已选择项目（自动包含 enterprise）
 * - 'parse'：需解析清单已确认（PARSE_CONFIRMED）
 * - 'format'：需格式清单已确认（FORMAT_CONFIRMED）
 * - 'material'：需素材清单已确认（MATERIAL_CONFIRMED）
 */
export type AccessLevel = 'public' | 'enterprise' | 'project' | 'parse' | 'format' | 'material'

export interface AccessRule {
  path: string
  access: AccessLevel
  /** 未满足时的提示文案 */
  denyReason: string
}

/** 路由访问规则表（与 App.tsx 路由一一对应） */
export const ACCESS_RULES: AccessRule[] = [
  { path: '/workspace', access: 'public', denyReason: '' },
  { path: '/settings', access: 'public', denyReason: '' },
  { path: '/materials', access: 'enterprise', denyReason: '请先选择企业' },
  { path: '/templates', access: 'enterprise', denyReason: '请先选择企业' },
  { path: '/project-home', access: 'project', denyReason: '请先选择项目' },
  { path: '/parse', access: 'project', denyReason: '请先选择项目' },
  { path: '/bid', access: 'parse', denyReason: '需先完成招标文件解析并确认清单' },
  { path: '/extract', access: 'format', denyReason: '需先完成格式清单确认' },
  { path: '/check', access: 'format', denyReason: '需先完成格式清单确认' },
  { path: '/template-match', access: 'material', denyReason: '需先完成素材提取清单确认' },
  { path: '/render', access: 'material', denyReason: '需先完成素材提取清单确认' },
]

/**
 * 检查当前状态是否满足指定 access 级别。
 */
export function canAccess(
  level: AccessLevel,
  state: {
    hasEnterprise: boolean
    hasProject: boolean
    parseConfirmed: boolean
    formatConfirmed: boolean
    materialConfirmed: boolean
  },
): boolean {
  switch (level) {
    case 'public':
      return true
    case 'enterprise':
      return state.hasEnterprise
    case 'project':
      return state.hasEnterprise && state.hasProject
    case 'parse':
      return state.hasEnterprise && state.hasProject && state.parseConfirmed
    case 'format':
      return state.hasEnterprise && state.hasProject && state.formatConfirmed
    case 'material':
      return state.hasEnterprise && state.hasProject && state.materialConfirmed
    default:
      return false
  }
}

/**
 * 获取当前路径的访问规则。
 */
export function getAccessRule(path: string): AccessRule | undefined {
  return ACCESS_RULES.find((r) => path.startsWith(r.path))
}

/**
 * 检查当前路径是否可访问；不可访问时返回 denyReason。
 */
export function checkPathAccess(
  path: string,
  state: Parameters<typeof canAccess>[1],
): { allowed: boolean; reason: string } {
  const rule = getAccessRule(path)
  if (!rule) return { allowed: true, reason: '' }
  const allowed = canAccess(rule.access, state)
  return { allowed, reason: allowed ? '' : rule.denyReason }
}

/** React Hook：获取当前 store 状态并检查路径访问权限 */
export function usePathAccess(path: string): { allowed: boolean; reason: string } {
  const hasEnterprise = useAppStore((s) => !!s.currentEnterprise)
  const hasProject = useAppStore((s) => !!s.currentProject)
  const parseConfirmed = useAppStore((s) => s.isParseConfirmed)
  const formatConfirmed = useAppStore((s) => s.isFormatListConfirmed)
  const materialConfirmed = useAppStore((s) => s.isMaterialConfirmed)

  return checkPathAccess(path, {
    hasEnterprise,
    hasProject,
    parseConfirmed,
    formatConfirmed,
    materialConfirmed,
  })
}
