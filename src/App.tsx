import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { Route, Routes } from 'react-router-dom'
import Home from './pages/Home'

export default function App() {
  return (
    <ConfigProvider locale={zhCN} theme={{ algorithm: theme.defaultAlgorithm }}>
      <Routes>
        <Route path="/" element={<Home />} />
      </Routes>
    </ConfigProvider>
  )
}
