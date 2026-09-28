import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import RequireUnlock from './components/RequireUnlock'
import WorkspacePage from './pages/workspace/WorkspacePage'
import ParsePage from './pages/parse/ParsePage'
import BidPage from './pages/bid/BidPage'
import CheckPage from './pages/check/CheckPage'
import SettingsPage from './pages/settings/SettingsPage'
import { useAppStore } from './stores/useAppStore'

export default function App() {
  const themeMode = useAppStore((s) => s.themeMode)

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: themeMode === 'light' ? theme.defaultAlgorithm : theme.darkAlgorithm,
      }}
    >
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/workspace" replace />} />
          <Route path="/workspace" element={<WorkspacePage />} />
          <Route path="/parse" element={<ParsePage />} />
          <Route element={<RequireUnlock />}>
            <Route path="/bid" element={<BidPage />} />
            <Route path="/check" element={<CheckPage />} />
          </Route>
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/workspace" replace />} />
        </Route>
      </Routes>
    </ConfigProvider>
  )
}
