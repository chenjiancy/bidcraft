import { MoonOutlined, SunOutlined } from '@ant-design/icons'
import { Button, Tooltip } from 'antd'
import { useAppStore } from '../stores/useAppStore'

export default function ThemeToggle() {
  const themeMode = useAppStore((s) => s.themeMode)
  const toggleTheme = useAppStore((s) => s.toggleTheme)

  return (
    <Tooltip title={themeMode === 'light' ? '切换到暗色主题' : '切换到亮色主题'}>
      <Button
        type="text"
        aria-label="切换主题"
        icon={themeMode === 'light' ? <MoonOutlined /> : <SunOutlined />}
        onClick={toggleTheme}
      />
    </Tooltip>
  )
}
