import { Layout, Menu, Tag } from 'antd'
import { useEffect } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { NAV_ITEMS } from './nav-config'
import { useAppStore } from '../stores/useAppStore'
import ThemeToggle from '../components/ThemeToggle'

const { Sider, Header, Content } = Layout

export default function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const themeMode = useAppStore((s) => s.themeMode)
  const isParseConfirmed = useAppStore((s) => s.isParseConfirmed)

  // 同步 data-theme 到根节点（驱动 CSS 变量与 Tailwind dark variant）
  useEffect(() => {
    document.documentElement.dataset.theme = themeMode
  }, [themeMode])

  return (
    <Layout className="h-full">
      <Sider
        width={224}
        className="border-r border-[var(--bc-border)]"
        style={{ background: 'var(--bc-sider-bg)' }}
      >
        <div
          className="flex h-16 items-center gap-2 px-5 text-base font-semibold"
          style={{ color: 'var(--bc-text)', borderBottom: '1px solid var(--bc-border)' }}
        >
          AI标书制作
        </div>
        <Menu
          mode="inline"
          theme={themeMode}
          selectedKeys={[location.pathname]}
          style={{ borderInlineEnd: 'none', background: 'transparent' }}
          onClick={({ key }) => navigate(key)}
          items={NAV_ITEMS.map((item) => ({
            key: item.path,
            icon: item.icon,
            label: item.label,
            disabled: item.requiresUnlock ? !isParseConfirmed : false,
          }))}
        />
      </Sider>

      <Layout style={{ background: 'var(--bc-content-bg)' }}>
        <Header
          className="flex items-center justify-end gap-3 border-b px-6"
          style={{
            background: 'var(--bc-header-bg)',
            borderColor: 'var(--bc-border)',
            height: 56,
          }}
        >
          {import.meta.env.DEV && <Tag color="blue">dev</Tag>}
          <ThemeToggle />
        </Header>
        <Content className="overflow-auto p-6">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
