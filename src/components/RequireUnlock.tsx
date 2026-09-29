import { Outlet } from 'react-router-dom'
import { useAppStore } from '../stores/useAppStore'
import LockedPage from './LockedPage'

/** 路由级门禁：未确认格式清单时拦截（含手工修改 hash 直跳的场景）。 */
export default function RequireUnlock() {
  const isParseConfirmed = useAppStore((s) => s.isParseConfirmed)
  const isFormatListConfirmed = useAppStore((s) => s.isFormatListConfirmed)
  return isParseConfirmed && isFormatListConfirmed ? <Outlet /> : <LockedPage />
}
