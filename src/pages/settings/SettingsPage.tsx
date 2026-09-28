import { Card, Descriptions, Segmented, Space, Typography } from 'antd'
import { MoonOutlined, SunOutlined } from '@ant-design/icons'
import { useAppStore } from '../../stores/useAppStore'

const { Title } = Typography

export default function SettingsPage() {
  const themeMode = useAppStore((s) => s.themeMode)
  const setThemeMode = useAppStore((s) => s.setThemeMode)

  return (
    <Space direction="vertical" size="middle" className="w-full">
      <Card>
        <Title level={5}>外观</Title>
        <Descriptions column={1}>
          <Descriptions.Item label="主题模式">
            <Segmented
              value={themeMode}
              onChange={(value) => setThemeMode(value as 'light' | 'dark')}
              options={[
                { value: 'light', label: '亮色', icon: <SunOutlined /> },
                { value: 'dark', label: '暗色', icon: <MoonOutlined /> },
              ]}
            />
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card>
        <Title level={5}>系统配置（占位）</Title>
        <Descriptions column={1}>
          <Descriptions.Item label="模型配置">
            云端/本地模型供应商、API Key（DPAPI）与测试连接将在 Task 6 实现
          </Descriptions.Item>
          <Descriptions.Item label="回收站清理">
            回收站保留时长配置将在 Task 21 完善（默认 30 天）
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </Space>
  )
}
