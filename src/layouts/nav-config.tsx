import { BankOutlined, SettingOutlined } from '@ant-design/icons'
import type { ReactNode } from 'react'

export interface NavItem {
  /** 同时作为路由路径与菜单 key */
  path: string
  label: string
  icon: ReactNode
}

/** 装饰性图标：aria-hidden 避免污染菜单项的 accessible name */
function decorative(icon: ReactNode): ReactNode {
  return <span aria-hidden="true">{icon}</span>
}

/**
 * 主导航（启动后首页仅保留工作入口）。
 * 解析/商务标/标书检查不进首页导航：经「企业/项目 → 进入项目」按项目流程进入，
 * 解析完成后由解析页内的入口按钮进入商务标制作/标书检查（FR-2 门禁不变）。
 */
export const NAV_ITEMS: NavItem[] = [
  { path: '/workspace', label: '企业/项目', icon: decorative(<BankOutlined />) },
]

/** 导航栏底部固定项 */
export const BOTTOM_NAV_ITEMS: NavItem[] = [
  { path: '/settings', label: '配置', icon: decorative(<SettingOutlined />) },
]
