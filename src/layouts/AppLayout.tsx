import { Menu, Tag, Tooltip } from 'antd'
import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { BOTTOM_NAV_ITEMS, NAV_LABELS, getNavGroups } from './nav-config'
import { useAppStore } from '../stores/useAppStore'
import ThemeToggle from '../components/ThemeToggle'
import TitleBar from './TitleBar'

/** 窗口背景材质：acrylic 由系统绘制；solid 时渲染层画渐变兜底 */
type WindowMaterial = 'acrylic' | 'solid'

export default function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const themeMode = useAppStore((s) => s.themeMode)
  const currentEnterprise = useAppStore((s) => s.currentEnterprise)
  const currentProject = useAppStore((s) => s.currentProject)
  const isParseConfirmed = useAppStore((s) => s.isParseConfirmed)
  const isFormatListConfirmed = useAppStore((s) => s.isFormatListConfirmed)
  const isMaterialConfirmed = useAppStore((s) => s.isMaterialConfirmed)
  const [material, setMaterial] = useState<WindowMaterial>('acrylic')

  // 同步 data-theme 到根节点（驱动 CSS 变量与 Tailwind dark variant）
  useEffect(() => {
    document.documentElement.dataset.theme = themeMode
  }, [themeMode])

  // 系统磨玻璃可用性由主进程判定（Win11 22H2+）；不可用时渲染层绘制渐变兜底背景
  useEffect(() => {
    let alive = true
    void window.bid?.win
      ?.getChrome()
      .then((chrome) => {
        if (alive) setMaterial(chrome.material)
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])

  // 原生窗口控件的符号色需跟随明暗主题，否则深色下按钮发黑不可见
  useEffect(() => {
    void window.bid?.win?.setTitleBarOverlay(themeMode === 'dark' ? '#edf2f8' : '#475569')
  }, [themeMode])

  const navGroups = getNavGroups({
    hasEnterprise: !!currentEnterprise,
    hasProject: !!currentProject,
    parseConfirmed: isParseConfirmed,
    formatConfirmed: isFormatListConfirmed,
    materialConfirmed: isMaterialConfirmed,
  })

  // 顶栏只显示当前模块名；「工作台」分区下同为一级页面，名字各自独立
  const crumb = NAV_LABELS[location.pathname] ?? '企业/项目'

  // 门禁进度提示：越靠后越接近可出标书
  const stage = !currentProject
    ? { text: '未选择项目', ok: false }
    : isMaterialConfirmed
      ? { text: '素材清单已确认', ok: true }
      : isFormatListConfirmed
        ? { text: '格式清单已确认', ok: true }
        : isParseConfirmed
          ? { text: '解析清单已确认', ok: true }
          : { text: '待解析招标文件', ok: false }

  return (
    <div className="bc-app" data-material={material}>
      <TitleBar />

      <div className="bc-body">
        <aside className="bc-sidebar">
          <div className="bc-scope">
            <span className="bc-scope-dot" aria-hidden="true" />
            <div className="bc-scope-who">
              <b>{currentEnterprise?.name ?? '未选择企业'}</b>
              <small>
                {currentProject?.name ?? (currentEnterprise ? '未选择项目' : '请先创建或选择企业')}
              </small>
            </div>
          </div>

          <nav className="bc-nav" aria-label="主导航">
            <Menu
              mode="inline"
              selectedKeys={[location.pathname]}
              onClick={({ key }) => navigate(key)}
              items={navGroups.map((group) => ({
                type: 'group' as const,
                key: group.label,
                label: group.label,
                children: group.items.map((item) => ({
                  key: item.path,
                  icon: item.icon,
                  disabled: item.disabled,
                  label: item.disabled ? (
                    <Tooltip title={item.disabledTooltip} placement="right">
                      <span>{item.label}</span>
                    </Tooltip>
                  ) : (
                    item.label
                  ),
                })),
              }))}
            />
          </nav>

          <div className="bc-nav-foot">
            <Menu
              mode="inline"
              selectedKeys={[location.pathname]}
              onClick={({ key }) => navigate(key)}
              items={BOTTOM_NAV_ITEMS.map((item) => ({
                key: item.path,
                icon: item.icon,
                label: item.label,
              }))}
            />
          </div>
        </aside>

        <div className="bc-main">
          <header className="bc-topbar">
            <div className="bc-crumb">
              <b>{crumb}</b>
            </div>
            <div className="bc-topbar-right">
              {import.meta.env.DEV && <Tag color="blue">dev</Tag>}
              <span className={stage.ok ? 'bc-pill bc-pill-ok' : 'bc-pill'}>
                <span className="bc-pill-dot" aria-hidden="true" />
                {stage.text}
              </span>
              <ThemeToggle />
            </div>
          </header>

          <main className="bc-content">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}
