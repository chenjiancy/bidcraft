import {
  CheckCircleOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  LoadingOutlined,
  SettingOutlined,
  UndoOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Divider,
  List,
  Progress,
  Radio,
  Space,
  Switch,
  Tag,
  Typography,
  message as antdMessage,
} from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getApiKey } from '../../api/modelConfig'
import {
  cancelParseTask,
  confirmParseChecklist,
  enterParseReview,
  getEngineStatus,
  getParseChecklist,
  getParseConfig,
  getParseStatus,
  registerSources,
  retryParseItem,
  startParse,
  updateParseConfig,
  type CheckpointItem,
  type EngineStatus,
  type LocalSourceFile,
  type LlmMode,
  type ParseChecklist,
  type ParseConfig,
  type ParseConfigSaveResult,
  type ParseEvent,
  type ParseStatus,
} from '../../api/parse'
import PagePlaceholder from '../../components/PagePlaceholder'
import { useAppStore } from '../../stores/useAppStore'
import { ParseChecklistReview } from './ParseChecklistReview'

const { Title, Text } = Typography

type Phase = 'loading' | 'idle' | 'running' | 'completed' | 'failed' | 'cancelled' | 'review'

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
  const setParseStatus = useAppStore((s) => s.setParseStatus)
  const navigate = useNavigate()

  const [phase, setPhase] = useState<Phase>('loading')
  const [engine, setEngine] = useState<EngineStatus | null>(null)
  const [status, setStatus] = useState<ParseStatus | null>(null)
  const [files, setFiles] = useState<LocalSourceFile[]>([])
  const [percent, setPercent] = useState(0)
  const [statusMsg, setStatusMsg] = useState('')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [config, setConfig] = useState<ParseConfig | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [llmEnabled, setLlmEnabled] = useState(false)
  const [llmMode, setLlmMode] = useState<LlmMode>('validate')
  const [reparseHint, setReparseHint] = useState(false)
  const [affectedItems, setAffectedItems] = useState<string[]>([])
  const [checklistData, setChecklistData] = useState<ParseChecklist | null>(null)

  const eid = currentEnterprise?.id ?? ''
  const pid = currentProject?.id ?? ''

  const requiredItems = useMemo(() => (config?.items ?? []).filter((i) => i.required), [config])
  const optionalItems = useMemo(() => (config?.items ?? []).filter((i) => !i.required), [config])
  const configDirty = useMemo(() => {
    if (!config) return false
    const sameSelection =
      config.items.every((i) => selected.has(i.key) === i.selected) &&
      selected.size === config.items.filter((i) => i.selected).length
    return (
      !sameSelection ||
      llmEnabled !== config.llm_enabled ||
      llmMode !== (config.llm_mode as LlmMode)
    )
  }, [config, selected, llmEnabled, llmMode])

  const applyConfig = useCallback((c: ParseConfig) => {
    setConfig(c)
    setSelected(new Set(c.items.filter((i) => i.selected).map((i) => i.key)))
    setLlmEnabled(c.llm_enabled)
    setLlmMode((c.llm_mode as LlmMode) ?? 'validate')
  }, [])

  const refreshStatus = useCallback(async () => {
    const s = await getParseStatus(eid, pid)
    setStatus(s)
    setParseStatus(s.parse_status)
    return s
  }, [eid, pid, setParseStatus])

  // 进入页面：引擎探针 + 已有解析状态 + 项目解析配置
  useEffect(() => {
    if (!currentProject || !currentEnterprise) return
    let cancelled = false
    void (async () => {
      try {
        const [eng, s, cfg] = await Promise.all([
          getEngineStatus(),
          getParseStatus(eid, pid),
          getParseConfig(eid, pid),
        ])
        if (cancelled) return
        setEngine(eng)
        setStatus(s)
        applyConfig(cfg)
        setParseStatus(s.parse_status)
        // PARSED / SCORE_PARSED / PARSE_REVIEW / PARSE_CONFIRMED 均视为解析完成
        if (
          s.parse_status === 'PARSED' ||
          s.parse_status === 'SCORE_PARSED' ||
          s.parse_status === 'PARSE_REVIEW' ||
          s.parse_status === 'PARSE_CONFIRMED'
        ) {
          setPhase('completed')
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
  }, [currentProject, currentEnterprise, eid, pid, setParseStatus, applyConfig])

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

  const toggleOptional = (key: string, checked: boolean): void => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (checked) next.add(key)
      else next.delete(key)
      return next
    })
  }

  /** 保存解析配置（TR-9.3/9.4）；返回保存结果（含受影响 checkpoint 项） */
  const saveConfig = async (): Promise<ParseConfigSaveResult> => {
    const result = await updateParseConfig(eid, pid, [...selected], llmEnabled, llmMode)
    applyConfig(result.config)
    if (Object.keys(result.changes).length > 0) {
      antdMessage.success('解析配置已保存')
    }
    setReparseHint(result.reparse_required)
    setAffectedItems(result.affected_items)
    return result
  }

  /** 解析前取 API Key：LLM 开启时缺失则阻断（TR-10.6 前置校验） */
  const resolveApiKey = async (): Promise<string | null> => {
    if (!llmEnabled) return null
    const key = await getApiKey()
    if (!key) {
      antdMessage.warning('已启用 LLM 辅助，请先在「模型配置」中设置 API Key 后再开始解析')
      return null
    }
    return key
  }

  /** 重置受影响要素项（PARSED 后配置变更）；返回是否已重置 */
  const resetAffected = async (keys: string[]): Promise<boolean> => {
    for (const key of keys) {
      await retryParseItem(eid, pid, key)
    }
    if (keys.length > 0) setAffectedItems([])
    return keys.length > 0
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

  const runStream = async (reparse = false, apiKey: string | null = null): Promise<void> => {
    setPhase('running')
    setPercent(0)
    setStatusMsg('启动解析任务…')
    setTaskId(null)
    const terminal = await startParse(eid, pid, reparse, handleProgress, apiKey)
    await refreshStatus()
    if (terminal.stage === 'completed') {
      setPhase('completed')
      setReparseHint(false)
      setAffectedItems([])
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
      const apiKey = await resolveApiKey()
      if (llmEnabled && !apiKey) return
      await runStream(true, apiKey)
    } finally {
      setBusy(false)
    }
  }

  /** 配置变更后的定向重跑：仅重置受影响要素项，物理层不动（TR-10.9） */
  const reparseAffected = async (): Promise<void> => {
    setBusy(true)
    try {
      const apiKey = await resolveApiKey()
      if (llmEnabled && !apiKey) return
      await resetAffected(affectedItems)
      await runStream(false, apiKey)
    } finally {
      setBusy(false)
    }
  }

  const start = async (): Promise<void> => {
    setBusy(true)
    try {
      const apiKey = await resolveApiKey()
      if (llmEnabled && !apiKey) return
      // 解析前先落库配置（FR-2：上传 → 配置 → 解析）
      if (config && configDirty) {
        setStatusMsg('保存解析配置…')
        const saved = await saveConfig()
        // PARSED 后变更：重置受影响要素项，避免续跑跳过导致产物过期
        if (saved.reparse_required) await resetAffected(saved.affected_items)
      }
      if (files.length > 0) {
        setStatusMsg('登记招标文件…')
        await registerSources(eid, pid, files)
      }
      await runStream(false, apiKey)
    } catch (err) {
      setPhase('failed')
      antdMessage.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const saveConfigClick = async (): Promise<void> => {
    setBusy(true)
    try {
      await saveConfig()
    } catch (err) {
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
      const apiKey = await resolveApiKey()
      if (llmEnabled && !apiKey) return
      await retryParseItem(eid, pid, item.key)
      await runStream(false, apiKey)
    } catch (err) {
      antdMessage.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const errorItems = status?.checkpoint?.items.filter((i) => i.state === 'error') ?? []
  const hasProgress = (status?.checkpoint?.items.length ?? 0) > 0
  const engineReady = engine?.available === true
  const configLocked = phase === 'running'

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

          {/* 解析配置（Task 9，TR-9.1/9.2） */}
          {config && phase !== 'loading' && (
            <Card
              size="small"
              title={
                <Space>
                  <SettingOutlined />
                  <span>解析配置</span>
                </Space>
              }
            >
              <Space direction="vertical" size="small" className="w-full">
                <div>
                  <Text strong>关键项（必选，不可取消）</Text>
                  <div>
                    {requiredItems.map((item) => (
                      <Checkbox key={item.key} checked disabled className="mt-1 mr-2">
                        {item.label}
                      </Checkbox>
                    ))}
                  </div>
                </div>
                <div>
                  <Text strong>其他项（按需勾选）</Text>
                  <div>
                    {optionalItems.map((item) => (
                      <Checkbox
                        key={item.key}
                        checked={selected.has(item.key)}
                        disabled={configLocked}
                        onChange={(e) => toggleOptional(item.key, e.target.checked)}
                        className="mt-1 mr-2"
                      >
                        {item.label}
                      </Checkbox>
                    ))}
                  </div>
                </div>

                <Divider className="my-2" />

                <Space align="start" wrap>
                  <Space>
                    <Switch
                      checked={llmEnabled}
                      disabled={configLocked}
                      onChange={(v) => setLlmEnabled(v)}
                      aria-label="启用 LLM 辅助"
                    />
                    <Text strong>启用 LLM 辅助</Text>
                  </Space>
                  <Radio.Group
                    value={llmMode}
                    disabled={!llmEnabled || configLocked}
                    onChange={(e) => setLlmMode(e.target.value as LlmMode)}
                    options={[
                      { value: 'validate', label: '校验模式' },
                      { value: 'dual_channel', label: '双通道模式（后续迭代）', disabled: true },
                    ]}
                    optionType="button"
                    buttonStyle="solid"
                  />
                  <Text type="secondary">
                    默认关闭（纯规则解析，无 LLM）；开启后当前仅支持校验模式，双通道模式后续迭代提供
                  </Text>
                </Space>

                <div>
                  <Button
                    size="small"
                    type={configDirty ? 'primary' : 'default'}
                    disabled={!configDirty || configLocked}
                    loading={busy}
                    onClick={() => void saveConfigClick()}
                  >
                    保存配置
                  </Button>
                  {config.is_default && !configDirty && (
                    <Text type="secondary" className="ml-2">
                      当前为默认配置，开始解析前将自动保存
                    </Text>
                  )}
                </div>
              </Space>
            </Card>
          )}

          {/* 进度区 */}
          {phase === 'running' && (
            <Space direction="vertical" size="small" className="w-full">
              <Progress percent={Math.round(percent)} status="active" />
              <Text type="secondary">{statusMsg || '准备中…'}</Text>
            </Space>
          )}

          {/* 配置变更提示（TR-9.4：PARSED 后改配置需重新解析生效；Task 10 定向重跑要素项） */}
          {phase !== 'running' && reparseHint && (
            <Alert
              type="warning"
              showIcon
              message="解析配置已变更，需重新解析后在提取结果中生效"
              description="物理解析结果（章节/OCR）不受影响；仅重新运行受影响的要素提取项。"
              action={
                <Space>
                  <Button
                    size="small"
                    type="primary"
                    loading={busy}
                    onClick={() => void reparseAffected()}
                  >
                    重新解析受影响项
                  </Button>
                  <Button size="small" loading={busy} onClick={() => void reparseAll()}>
                    全部重跑
                  </Button>
                </Space>
              }
            />
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

          {/* Task 13：解析清单复核 */}
          {phase === 'review' && checklistData && (
            <Card title="解析清单复核（逐条确认后保存解锁）">
              <ParseChecklistReview
                extraction={checklistData.extraction}
                score={checklistData.score}
                docx={checklistData.docx}
                enterpriseId={eid}
                projectId={pid}
                saving={busy}
                onCancel={() => {
                  setChecklistData(null)
                  setPhase('completed')
                }}
                onSave={async (payload) => {
                  setBusy(true)
                  try {
                    await confirmParseChecklist(eid, pid, payload)
                    await refreshStatus()
                    setChecklistData(null)
                    setPhase('completed')
                    antdMessage.success('解析清单已确认，业务模块已解锁')
                  } catch (err) {
                    antdMessage.error(err instanceof Error ? err.message : String(err))
                  } finally {
                    setBusy(false)
                  }
                }}
              />
            </Card>
          )}

          {/* 要素提取摘要（Task 10：规则粗分 + LLM 校验结果概览） */}
          {phase === 'completed' && status?.extraction && (
            <Card size="small" title="要素提取摘要">
              <Space wrap size="middle">
                <Text>
                  文档类型：<Tag color="blue">{status.extraction.doc_type ?? '未知'}</Tag>
                </Text>
                <Text>
                  勾选要素：{status.extraction.items_total} 项，成功提取{' '}
                  {status.extraction.items_extracted} 项
                </Text>
                <Text>
                  风险提示：
                  {status.extraction.red_flags > 0 ? (
                    <Tag color="error">{status.extraction.red_flags} 项</Tag>
                  ) : (
                    <Tag color="success">无</Tag>
                  )}
                </Text>
                {status.extraction.llm && (
                  <Text>
                    LLM 校验：<Tag>{String(status.extraction.llm.status ?? 'not_run')}</Tag>
                  </Text>
                )}
              </Space>
            </Card>
          )}

          {/* 评分表摘要（Task 11：评分办法解析结果概览；合计≠100 标红不阻断） */}
          {phase === 'completed' && status?.score && (
            <Card size="small" title="评分表摘要">
              <Space wrap size="middle">
                <Text>
                  评分大类：<Tag color="blue">{status.score.categories} 个</Tag>
                </Text>
                <Text>
                  合计分值：
                  {status.score.score_ok === false ? (
                    <Tag color="error">{status.score.total_score ?? '—'}（≠100，请核对）</Tag>
                  ) : (
                    <Tag color="success">{status.score.total_score ?? '—'}</Tag>
                  )}
                </Text>
                <Text>
                  风险提示：
                  {status.score.red_flags > 0 ? (
                    <Tag color="error">{status.score.red_flags} 项</Tag>
                  ) : (
                    <Tag color="success">无</Tag>
                  )}
                </Text>
                <Text>
                  结构校验：
                  {status.score.schema_validated ? (
                    <Tag color="success">已通过</Tag>
                  ) : (
                    <Tag color="warning">未通过</Tag>
                  )}
                </Text>
                {status.score.llm && (
                  <Text>
                    LLM 校验：<Tag>{String(status.score.llm.status ?? 'not_run')}</Tag>
                  </Text>
                )}
              </Space>
            </Card>
          )}

          {/* 投标文件格式摘要（Task 12：逐章 docx 导出概览；地址链接/人工增删留 Phase 1.2） */}
          {phase === 'completed' && status?.docx && (
            <Card size="small" title="投标文件格式（逐章 docx）">
              <Space wrap size="middle">
                <Text>
                  导出文档：
                  {status.docx.files > 0 ? (
                    <Tag color="blue">{status.docx.files} 个</Tag>
                  ) : (
                    <Tag>无</Tag>
                  )}
                </Text>
                <Text>
                  封面：
                  {status.docx.cover ? <Tag color="success">已导出</Tag> : <Tag>无</Tag>}
                </Text>
                <Text>
                  导出状态：
                  {status.docx.errors > 0 ? (
                    <Tag color="error">{status.docx.errors} 章失败（可单项重试）</Tag>
                  ) : status.docx.completed ? (
                    <Tag color="success">已完成</Tag>
                  ) : (
                    <Tag color="warning">未完成</Tag>
                  )}
                </Text>
                {status.docx.red_flags > 0 && (
                  <Text>
                    需对照原文件：<Tag color="warning">{status.docx.red_flags} 处</Tag>
                  </Text>
                )}
                {status.docx.missing_format_sources.length > 0 && (
                  <Text type="secondary">
                    未识别到「投标文件格式」章节：{status.docx.missing_format_sources.join('、')}
                  </Text>
                )}
              </Space>
            </Card>
          )}

          {/* 进入清单复核按钮 */}
          {phase === 'completed' &&
            !isParseConfirmed &&
            (status?.parse_status === 'SCORE_PARSED' ||
              status?.parse_status === 'PARSE_REVIEW') && (
              <Button
                type="primary"
                size="large"
                icon={<CheckCircleOutlined />}
                onClick={async () => {
                  setBusy(true)
                  try {
                    await enterParseReview(eid, pid)
                    const checklist = await getParseChecklist(eid, pid)
                    setChecklistData(checklist)
                    setPhase('review' as Phase)
                    await refreshStatus()
                  } catch (err) {
                    antdMessage.error(err instanceof Error ? err.message : String(err))
                  } finally {
                    setBusy(false)
                  }
                }}
                loading={busy}
              >
                进入清单复核（逐条确认后解锁）
              </Button>
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
                <Space>
                  <Button size="small" type="primary" onClick={() => navigate('/bid')}>
                    前往商务标制作
                  </Button>
                  <Button size="small" onClick={() => navigate('/check')}>
                    前往标书检查
                  </Button>
                </Space>
              }
            />
          ) : phase !== 'running' && phase !== 'review' ? (
            <Alert
              type="info"
              message="模块门禁：未确认"
              description="请完成解析后进入清单复核，逐条确认后保存解锁商务标制作与标书检查。"
            />
          ) : null}
        </Space>
      </Card>
    </Space>
  )
}
