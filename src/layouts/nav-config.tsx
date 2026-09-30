import {
  BankOutlined,
  CheckCircleOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'

export interface NavItem {
  /** 同时作为路由路径与菜单 key */
  path: string
  label: string
  icon: ReactNode
}

export interface NavItemWithAccess extends NavItem {
  /** 是否禁用（锁定） */
  disabled?: boolean
  /** 禁用时的 tooltip 提示 */
  disabledTooltip?: string
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
  { path: '/materials', label: '素材库', icon: decorative(<FolderOutlined />) },
  { path: '/templates', label: '模板库', icon: decorative(<FileTextOutlined />) },
]

/** 导航栏底部固定项 */
export const BOTTOM_NAV_ITEMS: NavItem[] = [
  { path: '/settings', label: '配置', icon: decorative(<SettingOutlined />) },
]

/**
 * 三层递进导航：根据 currentEnterprise / currentProject / parseConfirmed / formatConfirmed
 * 动态计算侧边栏可见项与锁定状态。
 *
 * 层级规则：
 * - 未选企业：仅显示「企业/项目」「配置」
 * - 已选企业未选项目：追加「素材库」「模板库」
 * - 已选项目：追加业务模块（解析/商务标/素材提取/标书检查/模板匹配/渲染），按门禁状态锁定
 */
export function getNavItems(opts: {
  hasEnterprise: boolean
  hasProject: boolean
  parseConfirmed: boolean
  formatConfirmed: boolean
  materialConfirmed: boolean
}): NavItemWithAccess[] {
  const items: NavItemWithAccess[] = [
    { path: '/workspace', label: '企业/项目', icon: decorative(<BankOutlined />) },
  ]

  if (opts.hasEnterprise) {
    items.push(
      { path: '/materials', label: '素材库', icon: decorative(<FolderOutlined />) },
      { path: '/templates', label: '模板库', icon: decorative(<FileTextOutlined />) },
    )
  }

  if (opts.hasProject) {
    items.push(
      {
        path: '/parse',
        label: '招标文件解析',
        icon: decorative(<FileSearchOutlined />),
      },
      {
        path: '/bid',
        label: '商务标制作',
        icon: decorative(<FolderOpenOutlined />),
        disabled: !opts.parseConfirmed,
        disabledTooltip: '需先完成招标文件解析并确认清单',
      },
      {
        path: '/extract',
        label: '素材提取',
        icon: decorative(<FolderOpenOutlined />),
        disabled: !opts.formatConfirmed,
        disabledTooltip: '需先完成格式清单确认',
      },
      {
        path: '/check',
        label: '标书检查',
        icon: decorative(<CheckCircleOutlined />),
        disabled: !opts.formatConfirmed,
        disabledTooltip: '需先完成格式清单确认',
      },
      {
        path: '/template-match',
        label: '模板匹配',
        icon: decorative(<FileTextOutlined />),
        disabled: !opts.materialConfirmed,
        disabledTooltip: '需先完成素材提取清单确认',
      },
      {
        path: '/render',
        label: '逐章渲染',
        icon: decorative(<FileTextOutlined />),
        disabled: !opts.materialConfirmed,
        disabledTooltip: '需先完成素材提取清单确认',
      },
    )
  }

  return items
}
