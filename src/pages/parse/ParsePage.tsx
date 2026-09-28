import {
  CheckCircleOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  LoadingOutlined,
  UndoOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  List,
  Progress,
  Space,
  Tag,
  Typography,
  message as antdMessage,
} from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  cancelParseTask,
  getEngineStatus,
  getParseStatus,
  registerSources,
  retryParseItem,
  startParse,
  type CheckpointItem,
  type EngineStatus,
  type LocalSourceFile,
  type ParseEvent,
  type ParseStatus,
} from '../../api/parse'
import PagePlaceholder from '../../components/PagePlaceholder'
import { useAppStore } from '../../stores/useAppStore'

const { Title, Text } = Typography

type Phase = 'loading' | 'idle' | 'running' | 'completed' | 'failed' | 'cancelled'

const STATE_COLOR: Record<string, string> = {
  success: 'success',
  error: 'error',
  running: 'processing',
  idle: 'default',
}

export default function ParsePage() {
  const currentEnterprise = useAppStore((s) => s.currentEnterprise)
  const currentProject = useAppStore((s) => s.currentProject)
  const isParseConfirmed = useAppStore((s) => s.isParseConfirmed)
  const setParseConfirmed = useAppStore((s) => s.setParseConfirmed)
  const navigate = useNavigate()

  const [phase, setPhase] = useState<Phase>('loading')
  const [engine, setEngine] = useState<EngineStatus | null>(null)
  const [status, setStatus] = useState<ParseStatus | null>(null)
  const [files, setFiles] = useState<LocalSourceFile[]>([])
  const [percent, setPercent] = useState(0)
  const [statusMsg, setStatusMsg] = useState('')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const eid = currentEnterprise?.id ?? ''
  const pid = currentProject?.id ?? ''

  const refreshStatus = useCallback(async () => {
    const s = await getParseStatus(eid, pid)
    setStatus(s)
    return s
  }, [eid, pid])

  // 进入页面：引擎探针 + 已有解析状态（支持断点续跑/已完成门禁恢复）
  useEffect(() => {
    if (!currentProject || !currentEnterprise) return
    let cancelled = false
    void (async () => {
      try {
        const [eng, s] = await Promise.all([getEngineStatus(), getParseStatus(eid, pid)])
        if (cancelled) return
        setEngine(eng)
        setStatus(s)
        if (s.parse_status === 'PARSED') {
          setPhase('completed')
          setParseConfirmed(true)
          setPercent(100)
        } else {
          setPhase('idle')
        }
      } catch (err) {
        if (!cancelled) {
          setPhase('idle')
          antdMessage.error(err instanceof Error ? err.message : String(err))
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [currentProject, currentEnterprise, eid, pid, setParseConfirmed])

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

  const pickFiles = async (): Promise<void> => {
    const picked = await window.bid.dialog.openBidFiles()
    if (picked.length === 0) return
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => f.path))
      return [...prev, ...picked.filter((f) => !seen.has(f.path))]
    })
  }

  const handleProgress = (event: ParseEvent): void => {
    // IPC 元事件：仅携带任务 ID（供取消），不是 SSE 业务事件
    if (event.stage === 'meta') {
      const id = event.extra?.taskId
      if (typeof id === 'string') setTaskId(id)
      return
    }
    setPercent(event.percent)
    setStatusMsg(event.message)
  }

  const runStream = async (reparse = false): Promise<void> => {
    setPhase('running')
    setPercent(0)
    setStatusMsg('启动解析任务…')
    setTaskId(null)
    const terminal = await startParse(eid, pid, reparse, handleProgress)
    await refreshStatus()
    if (terminal.stage === 'completed') {
      setPhase('completed')
      setParseConfirmed(true)
      antdMessage.success('招标文件解析完成')
    } else if (terminal.stage === 'cancelled') {
      setPhase('cancelled')
      antdMessage.warning('解析已取消，可从断点继续')
    } else {
      setPhase('failed')
      antdMessage.error(terminal.message || '解析失败，可重试未完成项')
    }
  }

  const reparseAll = async (): Promise<void> => {
    setBusy(true)
    try {
      await runStream(true)
    } finally {
      setBusy(false)
    }
  }

  const start = async (): Promise<void> => {
    setBusy(true)
    try {
      if (files.length > 0) {
        setStatusMsg('登记招标文件…')
        await registerSources(eid, pid, files)
      }
      await runStream(false)
    } catch (err) {
      setPhase('failed')
      antdMessage.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const cancel = async (): Promise<void> => {
    if (!taskId) return
    setBusy(true)
    try {
      await cancelParseTask(taskId)
    } finally {
      setBusy(false)
    }
  }

  const retryItem = async (item: CheckpointItem): Promise<void> => {
    setBusy(true)
    try {
      await retryParseItem(eid, pid, item.key)
      await runStream(false)
    } catch (err) {
      antdMessage.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const errorItems = status?.checkpoint?.items.filter((i) => i.state === 'error') ?? []
  const hasProgress = (status?.checkpoint?.items.length ?? 0) > 0
  const engineReady = engine?.available === true

  return (
    <Space direction="vertical" size="middle" className="w-full">
      <Card>
        <Space direction="vertical" size="middle" className="w-full">
          <Space>
            <Tag color="blue">{currentEnterprise.name}</Tag>
            <Tag color="geekblue">{currentProject.name}</Tag>
            {status && <Tag>{status.parse_status}</Tag>}
            {status?.running && <Tag color="processing">运行中</Tag>}
          </Space>

          <Title level={5}>招标文件解析</Title>
          <Text type="secondary">
            选择本机招标文件（PDF / Word / 扫描件），由 MinerU 解析为 Markdown 与带页码坐标的结构化
            JSON，并自动切分章节；同名多格式自动去重（docx &gt; doc &gt; pdf）。
          </Text>

          {engine && !engineReady && (
            <Alert
              type="error"
              showIcon
              message="解析引擎不可用"
              description={
                <Space direction="vertical" size={0}>
                  <Text>{engine.error ?? '未检测到 MinerU 运行环境'}</Text>
                  <Text type="secondary">
                    CUDA：{engine.cuda_available ? (engine.cuda_device ?? '可用') : '不可用'}；
                    LibreOffice：
                    {engine.libreoffice_available ? '已安装' : '未安装（.doc 转换需要）'}
                  </Text>
                </Space>
              }
            />
          )}

          {/* 文件选择（本机文件对话框，sidecar 同机复制入库） */}
          {phase !== 'running' && (
            <>
              <Space>
                <Button icon={<FolderOpenOutlined />} onClick={() => void pickFiles()}>
                  选择招标文件
                </Button>
                {files.length > 0 && (
                  <Button type="text" danger onClick={() => setFiles([])}>
                    清空
                  </Button>
                )}
              </Space>
              {files.length > 0 && (
                <List
                  size="small"
                  bordered
                  dataSource={files}
                  renderItem={(f) => (
                    <List.Item
                      actions={[
                        <a
                          key="remove"
                          onClick={() => setFiles((prev) => prev.filter((x) => x.path !== f.path))}
                        >
                          移除
                        </a>,
                      ]}
                    >
                      <Text>{f.name}</Text>
                    </List.Item>
                  )}
                />
              )}
            </>
          )}

          {/* 进度区 */}
          {phase === 'running' && (
            <Space direction="vertical" size="small" className="w-full">
              <Progress percent={Math.round(percent)} status="active" />
              <Text type="secondary">{statusMsg || '准备中…'}</Text>
            </Space>
          )}

          {/* 失败项（TR-8.7 单项重试） */}
          {(phase === 'failed' || phase === 'cancelled') && errorItems.length > 0 && (
            <List
              size="small"
              header={<Text strong>未完成项（可单项重试）</Text>}
              bordered
              dataSource={errorItems}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button
                      key="retry"
                      size="small"
                      type="link"
                      loading={busy}
                      onClick={() => void retryItem(item)}
                    >
                      重试
                    </Button>,
                  ]}
                >
                  <Space>
                    <Tag color="error">{item.state}</Tag>
                    <Text>{item.label}</Text>
                    {item.error && <Text type="secondary">{item.error}</Text>}
                  </Space>
                </List.Item>
              )}
            />
          )}

          {/* 操作按钮 */}
          {phase === 'running' ? (
            <Button danger onClick={() => void cancel()} disabled={!taskId || busy}>
              取消解析
            </Button>
          ) : (
            <Space wrap>
              <Button
                type="primary"
                size="large"
                icon={busy ? <LoadingOutlined /> : <CheckCircleOutlined />}
                loading={busy}
                disabled={!engineReady || (files.length === 0 && !hasProgress)}
                onClick={() => void start()}
              >
                {files.length > 0
                  ? '登记并开始解析'
                  : phase === 'failed' || phase === 'cancelled'
                    ? '从断点继续解析'
                    : '开始解析'}
              </Button>
              {phase === 'completed' && files.length === 0 && hasProgress && (
                <Button
                  icon={<UndoOutlined />}
                  loading={busy}
                  disabled={!engineReady}
                  onClick={() => void reparseAll()}
                >
                  重新解析全部（忽略已有结果）
                </Button>
              )}
            </Space>
          )}

          {/* Checkpoint 明细 */}
          {status?.checkpoint && phase !== 'running' && (
            <List
              size="small"
              header={
                <Text type="secondary">
                  Checkpoint：{status.checkpoint.state}（
                  {Object.entries(status.checkpoint.counts)
                    .map(([k, v]) => `${k} ${v}`)
                    .join(' / ')}
                  ）
                </Text>
              }
              dataSource={status.checkpoint.items}
              renderItem={(item) => (
                <List.Item>
                  <Space>
                    <Tag color={STATE_COLOR[item.state] ?? 'default'}>{item.state}</Tag>
                    <Text>{item.label}</Text>
                  </Space>
                </List.Item>
              )}
            />
          )}

          {/* 门禁状态 */}
          {isParseConfirmed && phase === 'completed' ? (
            <Alert
              type="success"
              showIcon
              icon={<CheckCircleOutlined />}
              message="解析清单已确认（PARSE_CONFIRMED）"
              description="商务标制作与标书检查模块已解锁。"
              action={
                <Button
                  size="small"
                  icon={<UndoOutlined />}
                  onClick={() => setParseConfirmed(false)}
                >
                  重置门禁
                </Button>
              }
            />
          ) : phase !== 'running' ? (
            <Alert
              type="info"
              message="模块门禁：未确认"
              description="解析完成（PARSED）后自动解锁商务标制作与标书检查。"
            />
          ) : null}
        </Space>
      </Card>
    </Space>
  )
}
