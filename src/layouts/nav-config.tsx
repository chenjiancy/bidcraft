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

/** 侧栏分区：工作台 / 企业资源 / 项目流程 */
export interface NavGroup {
  label: string
  items: NavItemWithAccess[]
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
export const NAV_LABELS: Record<string, string> = {
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

/** 项目流程顺序（已选项目时展示，按门禁状态锁定） */
const PROJECT_FLOW_ORDER = ['/parse', '/bid', '/extract', '/check', '/template-match', '/render']

/** 企业资源顺序（已选企业时展示） */
const ENTERPRISE_NAV_ORDER = ['/materials', '/templates']

/** 底部固定项 */
export const BOTTOM_NAV_ITEMS: NavItem[] = [
  { path: '/settings', label: '配置', icon: decorative(<SettingOutlined />) },
]

function plain(path: string): NavItemWithAccess {
  return { path, label: NAV_LABELS[path], icon: NAV_ICONS[path] }
}

/**
 * 三层递进导航：根据 currentEnterprise / currentProject / 门禁状态
 * 动态计算侧边栏分区与锁定状态，与路由 ACCESS_RULES 共用同一套 access 判断。
 *
 * 层级规则：
 * - 未选企业：仅「工作台 › 企业/项目」
 * - 已选企业未选项目：追加「企业资源」
 * - 已选项目：追加「项目首页」与「项目流程」，流程项按门禁状态锁定
 */
export function getNavGroups(opts: {
  hasEnterprise: boolean
  hasProject: boolean
  parseConfirmed: boolean
  formatConfirmed: boolean
  materialConfirmed: boolean
}): NavGroup[] {
  const state = {
    hasEnterprise: opts.hasEnterprise,
    hasProject: opts.hasProject,
    parseConfirmed: opts.parseConfirmed,
    formatConfirmed: opts.formatConfirmed,
    materialConfirmed: opts.materialConfirmed,
  }

  const workspace: NavItemWithAccess[] = [plain('/workspace')]
  if (opts.hasProject) workspace.push(plain('/project-home'))

  const groups: NavGroup[] = [{ label: '工作台', items: workspace }]

  if (opts.hasEnterprise) {
    groups.push({ label: '企业资源', items: ENTERPRISE_NAV_ORDER.map(plain) })
  }

  if (opts.hasProject) {
    groups.push({
      label: '项目流程',
      items: PROJECT_FLOW_ORDER.map((path) => {
        const rule = ACCESS_RULES.find((r) => r.path === path)
        const allowed = rule ? canAccess(rule.access, state) : false
        return {
          ...plain(path),
          disabled: !allowed,
          disabledTooltip: rule?.denyReason || undefined,
        }
      }),
    })
  }

  return groups.filter((g) => g.items.length > 0)
}
