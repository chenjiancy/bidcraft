import { Outlet } from 'react-router-dom'
import { useAppStore } from '../stores/useAppStore'
import LockedPage from './LockedPage'

interface Props {
  /**
   * 是否额外要求「格式清单已确认」（FORMAT_CONFIRMED）。
   * - true（默认）：用于素材提取/标书检查等业务模块；
   * - false：仅要求解析清单已确认（PARSE_CONFIRMED），用于商务标模块本身
   *   （格式清单复核在 /bid 内完成，此时尚未确认，不能拦）。
   */
  requireFormatConfirm?: boolean
}

/** 路由级门禁：未达到要求的状态时拦截（含手工修改 hash 直跳的场景）。 */
export default function RequireUnlock({ requireFormatConfirm = true }: Props) {
  const isParseConfirmed = useAppStore((s) => s.isParseConfirmed)
  const isFormatListConfirmed = useAppStore((s) => s.isFormatListConfirmed)
  const unlocked = isParseConfirmed && (!requireFormatConfirm || isFormatListConfirmed)
  return unlocked ? <Outlet /> : <LockedPage />
}
