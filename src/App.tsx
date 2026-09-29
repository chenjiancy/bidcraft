import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './layouts/AppLayout'
import RequireUnlock from './components/RequireUnlock'
import WorkspacePage from './pages/workspace/WorkspacePage'
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
          <Route path="/materials" element={<MaterialsPage />} />
          <Route path="/templates" element={<TemplatesPage />} />
          <Route path="/parse" element={<ParsePage />} />
          {/* 商务标模块：PARSE_CONFIRMED 即可进入（格式清单复核在页内完成） */}
          <Route element={<RequireUnlock requireFormatConfirm={false} />}>
            <Route path="/bid" element={<BidPage />} />
          </Route>
          {/* 素材提取/标书检查：需格式清单已确认（FORMAT_CONFIRMED） */}
          <Route element={<RequireUnlock />}>
            <Route path="/extract" element={<MaterialsExtractPage />} />
            <Route path="/check" element={<CheckPage />} />
            {/* 模板匹配与语义比对：MATERIAL_CONFIRMED 后进入（Task 18） */}
            <Route path="/template-match" element={<TemplateMatchPage />} />
            {/* 逐章渲染：READY_TO_RENDER 及之后可进入（Task 19） */}
            <Route path="/render" element={<RenderPage />} />
          </Route>
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/workspace" replace />} />
        </Route>
      </Routes>
    </ConfigProvider>
  )
}
