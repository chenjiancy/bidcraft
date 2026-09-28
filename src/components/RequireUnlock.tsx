import { Outlet } from 'react-router-dom'
import { useAppStore } from '../stores/useAppStore'
import LockedPage from './LockedPage'

/** 路由级门禁：未确认解析清单时拦截（含手工修改 hash 直跳的场景）。 */
export default function RequireUnlock() {
  const isParseConfirmed = useAppStore((s) => s.isParseConfirmed)
  return isParseConfirmed ? <Outlet /> : <LockedPage />
}
