import {
  BankOutlined,
  CheckCircleOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  HomeOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'
import { ACCESS_RULES, canAccess } from '../access'

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

/** 导航项图标映射（按 path） */
const NAV_ICONS: Record<string, ReactNode> = {
  '/workspace': decorative(<BankOutlined />),
  '/project-home': decorative(<HomeOutlined />),
  '/parse': decorative(<FileSearchOutlined />),
  '/bid': decorative(<FolderOpenOutlined />),
  '/extract': decorative(<FolderOpenOutlined />),
  '/check': decorative(<CheckCircleOutlined />),
  '/template-match': decorative(<FileTextOutlined />),
  '/render': decorative(<FileTextOutlined />),
  '/materials': decorative(<FolderOutlined />),
  '/templates': decorative(<FileTextOutlined />),
  '/settings': decorative(<SettingOutlined />),
}

/** 导航项显示名称（按 path） */
const NAV_LABELS: Record<string, string> = {
  '/workspace': '企业/项目',
  '/project-home': '项目首页',
  '/parse': '招标文件解析',
  '/bid': '商务标制作',
  '/extract': '素材提取',
  '/check': '标书检查',
  '/template-match': '模板匹配',
  '/render': '逐章渲染',
  '/materials': '素材库',
  '/templates': '模板库',
  '/settings': '配置',
}

/** 侧边栏展示顺序（已选项目时） */
const PROJECT_NAV_ORDER = [
  '/project-home',
  '/parse',
  '/bid',
  '/extract',
  '/check',
  '/template-match',
  '/render',
]

/** 已选企业但未选项目时展示的项 */
const ENTERPRISE_NAV_ORDER = ['/materials', '/templates']

/** 底部固定项 */
export const BOTTOM_NAV_ITEMS: NavItem[] = [
  { path: '/settings', label: '配置', icon: decorative(<SettingOutlined />) },
]

/**
 * 三层递进导航：根据 currentEnterprise / currentProject / 门禁状态
 * 动态计算侧边栏可见项与锁定状态，与路由 ACCESS_RULES 共用同一套 access 判断。
 *
 * 层级规则：
 * - 未选企业：仅显示「企业/项目」
 * - 已选企业未选项目：追加「素材库」「模板库」
 * - 已选项目：追加业务模块，按门禁状态锁定
 */
export function getNavItems(opts: {
  hasEnterprise: boolean
  hasProject: boolean
  parseConfirmed: boolean
  formatConfirmed: boolean
  materialConfirmed: boolean
}): NavItemWithAccess[] {
  const state = {
    hasEnterprise: opts.hasEnterprise,
    hasProject: opts.hasProject,
    parseConfirmed: opts.parseConfirmed,
    formatConfirmed: opts.formatConfirmed,
    materialConfirmed: opts.materialConfirmed,
  }

  const items: NavItemWithAccess[] = [
    { path: '/workspace', label: '企业/项目', icon: decorative(<BankOutlined />) },
  ]

  if (opts.hasEnterprise) {
    for (const path of ENTERPRISE_NAV_ORDER) {
      items.push({
        path,
        label: NAV_LABELS[path],
        icon: NAV_ICONS[path],
      })
    }
  }

  if (opts.hasProject) {
    for (const path of PROJECT_NAV_ORDER) {
      const rule = ACCESS_RULES.find((r) => r.path === path)
      const allowed = rule ? canAccess(rule.access, state) : false
      items.push({
        path,
        label: NAV_LABELS[path],
        icon: NAV_ICONS[path],
        disabled: !allowed,
        disabledTooltip: rule?.denyReason || undefined,
      })
    }
  }

  return items
}
