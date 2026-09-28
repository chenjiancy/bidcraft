import { FileSearchOutlined, CheckCircleOutlined, UndoOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Space, Tag, Typography, Upload } from 'antd'
import type { UploadFile } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PagePlaceholder from '../../components/PagePlaceholder'
import { useAppStore } from '../../stores/useAppStore'

const { Title, Text } = Typography

export default function ParsePage() {
  const currentEnterprise = useAppStore((s) => s.currentEnterprise)
  const currentProject = useAppStore((s) => s.currentProject)
  const isParseConfirmed = useAppStore((s) => s.isParseConfirmed)
  const setParseConfirmed = useAppStore((s) => s.setParseConfirmed)
  const navigate = useNavigate()
  const [fileList, setFileList] = useState<UploadFile[]>([])

  // 未选择项目时提示
  if (!currentProject || !currentEnterprise) {
    return (
      <Card>
        <PagePlaceholder
          icon={<FileSearchOutlined />}
          title="招标文件解析"
          description={
            <Space direction="vertical">
              <Text>请先选择企业和项目后进入解析流程。</Text>
              <Button type="primary" onClick={() => navigate('/workspace')}>
                前往企业/项目
              </Button>
            </Space>
          }
        />
      </Card>
    )
  }

  return (
    <Space direction="vertical" size="middle" className="w-full">
      <Card>
        <Space direction="vertical" size="middle" className="w-full">
          {/* 项目上下文 */}
          <Space>
            <Tag color="blue">{currentEnterprise.name}</Tag>
            <Tag color="geekblue">{currentProject.name}</Tag>
          </Space>

          <Title level={5}>招标文件解析</Title>
          <Text type="secondary">
            上传招标文件（PDF / Word / 扫描件），实际解析功能将在阶段 1.1（Task 8+）实现。 当前为
            Walking Skeleton 集成验证阶段。
          </Text>

          {/* 文件上传区 */}
          <Upload.Dragger
            fileList={fileList}
            beforeUpload={(file) => {
              setFileList((prev) => [...prev, file as UploadFile])
              return false
            }}
            onRemove={(file) => {
              setFileList((prev) => prev.filter((f) => f.uid !== file.uid))
            }}
            accept=".pdf,.doc,.docx"
            multiple
          >
            <p className="ant-upload-drag-icon">
              <FileSearchOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽招标文件到此处</p>
            <p className="ant-upload-hint">支持 PDF / Word / 扫描件（可多选）</p>
          </Upload.Dragger>

          {/* 确认状态 */}
          {isParseConfirmed ? (
            <Alert
              type="success"
              showIcon
              icon={<CheckCircleOutlined />}
              message="解析清单已确认（PARSE_CONFIRMED）"
              description="商务标制作与标书检查模块已解锁。实际解析功能将在阶段 1.1 实现。"
              action={
                <Button
                  size="small"
                  icon={<UndoOutlined />}
                  onClick={() => setParseConfirmed(false)}
                >
                  重置
                </Button>
              }
            />
          ) : (
            <Alert
              type="info"
              message="模块门禁：未确认"
              description="商务标制作与标书检查当前为置灰状态。确认解析清单后将解锁。"
            />
          )}

          {/* 模拟确认按钮 */}
          {!isParseConfirmed && (
            <Button
              type="primary"
              size="large"
              icon={<CheckCircleOutlined />}
              onClick={() => setParseConfirmed(true)}
              disabled={fileList.length === 0}
            >
              模拟确认解析清单（PARSE_CONFIRMED）
            </Button>
          )}
          {fileList.length === 0 && !isParseConfirmed && (
            <Text type="secondary">请先上传至少一个招标文件</Text>
          )}
        </Space>
      </Card>
    </Space>
  )
}
