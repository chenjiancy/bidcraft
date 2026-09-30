import { Outlet, useLocation } from 'react-router-dom'
import { checkPathAccess } from '../access'
import { useAppStore } from '../stores/useAppStore'
import LockedPage from './LockedPage'

/**
 * 路由级统一门禁：基于 access.ts 的 ACCESS_RULES 判断当前路径是否可访问。
 * 替代手动维护的 RequireUnlock，路由与菜单共用同一套规则。
 */
export default function AccessGuard() {
  const location = useLocation()
  const hasEnterprise = useAppStore((s) => !!s.currentEnterprise)
  const hasProject = useAppStore((s) => !!s.currentProject)
  const parseConfirmed = useAppStore((s) => s.isParseConfirmed)
  const formatConfirmed = useAppStore((s) => s.isFormatListConfirmed)
  const materialConfirmed = useAppStore((s) => s.isMaterialConfirmed)

  const { allowed, reason } = checkPathAccess(location.pathname, {
    hasEnterprise,
    hasProject,
    parseConfirmed,
    formatConfirmed,
    materialConfirmed,
  })

  return allowed ? <Outlet /> : <LockedPage reason={reason} />
}
