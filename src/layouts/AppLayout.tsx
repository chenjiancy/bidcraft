import { Layout, Menu, Tag, Tooltip } from 'antd'
import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { BOTTOM_NAV_ITEMS, getNavItems } from './nav-config'
import { useAppStore } from '../stores/useAppStore'
import ThemeToggle from '../components/ThemeToggle'
import UpdateBanner from '../components/UpdateBanner'

export default function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const themeMode = useAppStore((s) => s.themeMode)
  const currentEnterprise = useAppStore((s) => s.currentEnterprise)
  const currentProject = useAppStore((s) => s.currentProject)
  const isParseConfirmed = useAppStore((s) => s.isParseConfirmed)
  const isFormatListConfirmed = useAppStore((s) => s.isFormatListConfirmed)
  const isMaterialConfirmed = useAppStore((s) => s.isMaterialConfirmed)
  const [version, setVersion] = useState<string>('')

  // 同步 data-theme 到根节点（驱动 CSS 变量与 Tailwind dark variant）
  useEffect(() => {
    document.documentElement.dataset.theme = themeMode
  }, [themeMode])

  // 获取应用版本号
  useEffect(() => {
    void window.bid?.app?.getVersion().then(setVersion)
  }, [])

  const navItems = getNavItems({
    hasEnterprise: !!currentEnterprise,
    hasProject: !!currentProject,
    parseConfirmed: isParseConfirmed,
    formatConfirmed: isFormatListConfirmed,
    materialConfirmed: isMaterialConfirmed,
  })

  // 原生窗口控件的符号色需跟随明暗主题，否则深色下按钮发黑不可见
  useEffect(() => {
    void window.bid?.win?.setTitleBarOverlay(themeMode === 'dark' ? '#edf2f8' : '#475569')
  }, [themeMode])

  return (
    <Layout className="h-full">
      <Layout.Sider
        width={224}
        className="border-r border-[var(--bc-border)]"
        style={{ background: 'var(--bc-sider-bg)' }}
      >
        <div className="flex h-full flex-col">
          <div
            className="flex h-16 shrink-0 items-center gap-2 px-5 text-base font-semibold"
            style={{ color: 'var(--bc-text)', borderBottom: '1px solid var(--bc-border)' }}
          >
            AI标书制作
          </div>
          <Menu
            mode="inline"
            theme={themeMode}
            selectedKeys={[location.pathname]}
            className="flex-1 overflow-auto"
            style={{ borderInlineEnd: 'none', background: 'transparent' }}
            onClick={({ key }) => navigate(key)}
            items={navItems.map((item) => ({
              key: item.path,
              icon: item.icon,
              label: item.disabled ? (
                <Tooltip title={item.disabledTooltip} placement="right">
                  {/* 命中区须撑满菜单行：antd Tooltip 只监听其直接子元素，
                      行内 span 仅覆盖文字宽度，行中部 hover 不触发提示 */}
                  <span
                    data-testid="nav-locked-tooltip-trigger"
                    style={{ display: 'block', width: '100%' }}
                  >
                    {item.label}
                  </span>
                </Tooltip>
              ) : (
                item.label
              ),
              disabled: item.disabled,
            }))}
          />
          <Menu
            mode="inline"
            theme={themeMode}
            selectedKeys={[location.pathname]}
            className="shrink-0"
            style={{
              borderInlineEnd: 'none',
              background: 'transparent',
              borderTop: '1px solid var(--bc-border)',
            }}
            onClick={({ key }) => navigate(key)}
            items={BOTTOM_NAV_ITEMS.map((item) => ({
              key: item.path,
              icon: item.icon,
              label: item.label,
            }))}
          />
          {version && (
            <div
              className="px-5 py-2 text-xs"
              style={{ color: 'var(--text-3)', borderTop: '1px solid var(--bc-border)' }}
            >
              v{version}
            </div>
          )}
        </div>
      </Layout.Sider>

      <Layout>
        <Layout.Header className="flex items-center justify-between px-4 border-b border-[var(--bc-border)] bc-titlebar-region">
          <div className="font-medium" style={{ color: 'var(--bc-text)' }}>
            {location.pathname === '/workspace' ? '企业/项目' : location.pathname || ''}
          </div>
          <div className="flex items-center gap-3 bc-titlebar-no-drag">
            {import.meta.env.DEV && <Tag color="blue">dev</Tag>}
            <ThemeToggle />
          </div>
        </Layout.Header>
        <Layout.Content
          className="bc-content"
          style={{ flex: 1, minWidth: 0, position: 'relative' }}
        >
          <UpdateBanner />
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
  )
}
