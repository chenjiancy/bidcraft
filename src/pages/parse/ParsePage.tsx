import { FileSearchOutlined } from '@ant-design/icons'
import { Alert, Button, Space, Typography } from 'antd'
import PagePlaceholder from '../../components/PagePlaceholder'
import { useAppStore } from '../../stores/useAppStore'

const { Text } = Typography

export default function ParsePage() {
  const isParseConfirmed = useAppStore((s) => s.isParseConfirmed)
  const setParseConfirmed = useAppStore((s) => s.setParseConfirmed)

  return (
    <PagePlaceholder
      icon={<FileSearchOutlined />}
      title="招标文件解析"
      description={
        <Space direction="vertical">
          <span>
            PDF / Word / 扫描件上传、MinerU 解析、清单人工确认将在阶段 1.1（Task 8+）实现。
          </span>
          <Text type="warning">
            下方为开发期临时占位控件：用于 Task 2 验证门禁与主题；Task 7
            将由真实项目状态机替换并移除。
          </Text>
        </Space>
      }
      extra={
        isParseConfirmed ? (
          <Space direction="vertical">
            <Alert type="success" showIcon message="（模拟）解析清单已确认，业务模块已解锁" />
            <Button onClick={() => setParseConfirmed(false)}>模拟退回未确认状态</Button>
          </Space>
        ) : (
          <Button type="primary" onClick={() => setParseConfirmed(true)}>
            模拟确认解析清单（临时）
          </Button>
        )
      }
    />
  )
}
