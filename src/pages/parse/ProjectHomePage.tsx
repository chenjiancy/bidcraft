import {
  CheckCircleOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  LockOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { Button, Card, Col, Row, Space, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import PagePlaceholder from '../../components/PagePlaceholder'
import { useAppStore } from '../../stores/useAppStore'

const { Title, Text } = Typography

interface ModuleCard {
  key: string
  title: string
  description: string
  icon: React.ReactNode
  path: string
  disabled: boolean
  disabledReason: string
  status: 'locked' | 'ready' | 'completed' | 'in-progress'
  statusText: string
}

export default function ProjectHomePage() {
  const navigate = useNavigate()
  const currentEnterprise = useAppStore((s) => s.currentEnterprise)
  const currentProject = useAppStore((s) => s.currentProject)
  const isParseConfirmed = useAppStore((s) => s.isParseConfirmed)
  const isFormatListConfirmed = useAppStore((s) => s.isFormatListConfirmed)
  const isMaterialConfirmed = useAppStore((s) => s.isMaterialConfirmed)
  const parseStatus = useAppStore((s) => s.parseStatus)

  if (!currentProject || !currentEnterprise) {
    return (
      <Card>
        <PagePlaceholder
          icon={<FileSearchOutlined />}
          title="项目工作台"
          description={
            <Space direction="vertical">
              <Text>请先选择企业和项目后进入业务模块。</Text>
              <Button type="primary" onClick={() => navigate('/workspace')}>
                前往企业/项目
              </Button>
            </Space>
          }
        />
      </Card>
    )
  }

  const modules: ModuleCard[] = [
    {
      key: 'parse',
      title: '招标文件解析',
      description: '上传招标文件，解析为结构化清单与评分表',
      icon: <FileSearchOutlined />,
      path: '/parse',
      disabled: false,
      disabledReason: '',
      status: isParseConfirmed ? 'completed' : 'ready',
      statusText: isParseConfirmed ? '已完成' : '开始',
    },
    {
      key: 'bid',
      title: '商务标制作',
      description: '基于解析清单制作商务标书',
      icon: <FolderOpenOutlined />,
      path: '/bid',
      disabled: !isParseConfirmed,
      disabledReason: '需先完成招标文件解析',
      status: isParseConfirmed ? 'ready' : 'locked',
      statusText: isParseConfirmed ? '进入' : '未解锁',
    },
    {
      key: 'extract',
      title: '素材提取',
      description: '提取商务标所需素材并匹配素材库',
      icon: <FolderOpenOutlined />,
      path: '/extract',
      disabled: !isFormatListConfirmed,
      disabledReason: '需先完成格式清单确认',
      status: isFormatListConfirmed ? (isMaterialConfirmed ? 'completed' : 'ready') : 'locked',
      statusText: isFormatListConfirmed ? (isMaterialConfirmed ? '已完成' : '进入') : '未解锁',
    },
    {
      key: 'check',
      title: '标书检查',
      description: '检查标书完整性与合规性',
      icon: <CheckCircleOutlined />,
      path: '/check',
      disabled: !isFormatListConfirmed,
      disabledReason: '需先完成格式清单确认',
      status: isFormatListConfirmed ? 'ready' : 'locked',
      statusText: isFormatListConfirmed ? '进入' : '未解锁',
    },
    {
      key: 'template-match',
      title: '模板匹配',
      description: '匹配标书模板并进行语义比对',
      icon: <SettingOutlined />,
      path: '/template-match',
      disabled: !isMaterialConfirmed,
      disabledReason: '需先完成素材提取清单确认',
      status: isMaterialConfirmed ? 'ready' : 'locked',
      statusText: isMaterialConfirmed ? '进入' : '未解锁',
    },
    {
      key: 'render',
      title: '逐章渲染',
      description: '按章节渲染最终标书文档',
      icon: <FileSearchOutlined />,
      path: '/render',
      disabled: !isMaterialConfirmed,
      disabledReason: '需先完成素材提取清单确认',
      status: isMaterialConfirmed ? 'ready' : 'locked',
      statusText: isMaterialConfirmed ? '进入' : '未解锁',
    },
  ]

  const statusColor = (s: string) => {
    switch (s) {
      case 'completed':
        return 'success'
      case 'ready':
        return 'processing'
      case 'in-progress':
        return 'warning'
      default:
        return 'default'
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* 项目信息头部 */}
      <Card className="bc-page-hero">
        <Space direction="vertical" size="small">
          <Space>
            <Tag color="blue">{currentEnterprise.name}</Tag>
            <Tag color="geekblue">{currentProject.name}</Tag>
            {parseStatus && <Tag>{parseStatus}</Tag>}
          </Space>
          <Title level={4} style={{ margin: 0 }}>
            项目工作台
          </Title>
          <Text type="secondary">按顺序完成各业务模块，解析完成后自动解锁后续模块。</Text>
        </Space>
      </Card>

      {/* 模块卡片网格 */}
      <Row gutter={[16, 16]}>
        {modules.map((m) => (
          <Col key={m.key} xs={24} sm={12} lg={8}>
            <Card
              className={[
                'bc-module-card',
                m.disabled ? 'is-locked' : '',
                !m.disabled && m.status === 'completed' ? 'is-completed' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              hoverable={!m.disabled}
              onClick={() => !m.disabled && navigate(m.path)}
              style={{ height: '100%', cursor: m.disabled ? 'not-allowed' : 'pointer' }}
            >
              <div className="bc-module-head">
                <span className="bc-module-icon">{m.icon}</span>
                <div className="bc-module-text">
                  <Title level={5} style={{ margin: 0 }}>
                    {m.title}
                  </Title>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {m.description}
                  </Text>
                </div>
              </div>
              <div className="bc-module-foot">
                <Tag color={statusColor(m.status)}>{m.statusText}</Tag>
                {m.disabled ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <LockOutlined /> {m.disabledReason}
                  </Text>
                ) : (
                  <Button type="link" size="small" style={{ padding: 0 }}>
                    进入 →
                  </Button>
                )}
              </div>
            </Card>
          </Col>
        ))}
      </Row>
    </Space>
  )
}
