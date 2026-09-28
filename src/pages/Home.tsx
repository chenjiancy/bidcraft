import { Card, Descriptions, Tag, Typography } from 'antd'
import { useEffect, useState } from 'react'

const { Title, Paragraph } = Typography

export default function Home() {
  const isDev = import.meta.env.DEV
  const [version, setVersion] = useState('')
  const [userDataPath, setUserDataPath] = useState('')

  useEffect(() => {
    window.bid.app.getVersion().then(setVersion)
    window.bid.app.getUserDataPath().then(setUserDataPath)
  }, [])

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100 p-6">
      <Card className="w-full max-w-2xl">
        <Title level={3}>AI标书制作</Title>
        <Paragraph type="secondary">阶段 1.0 Walking Skeleton · 项目骨架</Paragraph>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="环境标识">
            {/* data-testid 供 E2E 断言 dev/prod 分流 */}
            <Tag data-testid="env-name" color={isDev ? 'blue' : 'green'}>
              {isDev ? 'BidCraft-dev' : 'BidCraftApp'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="版本">{version}</Descriptions.Item>
          <Descriptions.Item label="userData 路径">{userDataPath}</Descriptions.Item>
        </Descriptions>
        <Paragraph type="secondary" className="mt-4">
          Python sidecar 由主进程自动拉起（仅 127.0.0.1）。
        </Paragraph>
      </Card>
    </div>
  )
}
