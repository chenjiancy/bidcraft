import {
  AuditOutlined,
  BankOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'

export interface NavItem {
  /** 同时作为路由路径与菜单 key */
  path: string
  label: string
  icon: ReactNode
  /** 需要解析清单确认后才解锁（FR-2 门禁） */
  requiresUnlock?: boolean
}

/** 装饰性图标：aria-hidden 避免污染菜单项的 accessible name */
function decorative(icon: ReactNode): ReactNode {
  return <span aria-hidden="true">{icon}</span>
}

export const NAV_ITEMS: NavItem[] = [
  { path: '/workspace', label: '企业/项目', icon: decorative(<BankOutlined />) },
  { path: '/parse', label: '招标文件解析', icon: decorative(<FileSearchOutlined />) },
  {
    path: '/bid',
    label: '商务标制作',
    icon: decorative(<FileTextOutlined />),
    requiresUnlock: true,
  },
  {
    path: '/check',
    label: '标书检查',
    icon: decorative(<AuditOutlined />),
    requiresUnlock: true,
  },
  { path: '/settings', label: '配置', icon: decorative(<SettingOutlined />) },
]
