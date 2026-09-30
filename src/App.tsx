import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import AccessGuard from './components/AccessGuard'
import WorkspacePage from './pages/workspace/WorkspacePage'
import ProjectHomePage from './pages/parse/ProjectHomePage'
import ParsePage from './pages/parse/ParsePage'
import BidPage from './pages/bid/BidPage'
import CheckPage from './pages/check/CheckPage'
import MaterialsPage from './pages/materials/MaterialsPage'
import MaterialsExtractPage from './pages/extract/MaterialsExtractPage'
import TemplatesPage from './pages/templates/TemplatesPage'
import TemplateMatchPage from './pages/template-match/TemplateMatchPage'
import RenderPage from './pages/render/RenderPage'
import SettingsPage from './pages/settings/SettingsPage'
import { useAppStore } from './stores/useAppStore'

/** 正文字体栈，与 main.css 的 --font-ui 保持一致 */
const UI_FONT_FAMILY =
  "'Segoe UI Variable Text', 'Segoe UI', 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif"

export default function App() {
  const themeMode = useAppStore((s) => s.themeMode)

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: themeMode === 'light' ? theme.defaultAlgorithm : theme.darkAlgorithm,
        token: {
          // 强调色：青绿（呼应"雾面玻璃 × 公文书卷"的克制调性）
          colorPrimary: themeMode === 'light' ? '#0d9488' : '#2dd4bf',
          borderRadius: 10,
          fontFamily: UI_FONT_FAMILY,
        },
      }}
    >
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/workspace" replace />} />
          <Route path="/workspace" element={<WorkspacePage />} />
          <Route path="/materials" element={<MaterialsPage />} />
          <Route path="/templates" element={<TemplatesPage />} />
          {/* 项目首页：进入项目后的默认页，展示模块卡片与解锁状态 */}
          <Route path="/project-home" element={<ProjectHomePage />} />
          <Route path="/parse" element={<ParsePage />} />
          {/* 统一门禁：AccessGuard 根据 access.ts 规则拦截未解锁模块 */}
          <Route element={<AccessGuard />}>
            <Route path="/bid" element={<BidPage />} />
            <Route path="/extract" element={<MaterialsExtractPage />} />
            <Route path="/check" element={<CheckPage />} />
            <Route path="/template-match" element={<TemplateMatchPage />} />
            <Route path="/render" element={<RenderPage />} />
          </Route>
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/workspace" replace />} />
        </Route>
      </Routes>
    </ConfigProvider>
  )
}
