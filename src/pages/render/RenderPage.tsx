/**
 * Task 19：逐章渲染页。
 *
 * 流程（READY_TO_RENDER 之后）：
 *  1. 查看渲染计划（全章节 + 占位符预览）
 *  2. B 类占位人工取值调整（多候选时拦截标红）
 *  3. 统一确认渲染计划 → 启动渲染（SSE 进度流）
 *  4. 渲染完成后展示警告清单 + 一致性审计结果
 *  5. 下载各章节渲染产物
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  message,
  Popconfirm,
  Progress,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  confirmRenderPlan,
  getAuditResult,
  getRenderPlan,
  getRenderStatus,
  getWarnings,
  startRender,
  cancelRender,
  downloadChapter,
  type AuditResult,
  type RenderPlan,
  type RenderPlanItem,
  type RenderProgressEvent,
  type RenderStatus,
  type WarningList,
  type BClassAdjustment,
} from '../../api/render'
import { useAppStore } from '../../stores/useAppStore'

const { Text, Title } = Typography
const { Search } = Input

// ---------- B 类占位调整行状态 ----------

interface BAdjustRow {
  chapter: string
  placeholder: string
  description: string
  value: string
  needs_manual: boolean
}

export default function RenderPage() {
  const currentEnterprise = useAppStore((s) => s.currentEnterprise)
  const currentProject = useAppStore((s) => s.currentProject)
  const setParseStatus = useAppStore((s) => s.setParseStatus)
  const navigate = useNavigate()

  const [plan, setPlan] = useState<RenderPlan | null>(null)
  const [status, setStatus] = useState<RenderStatus | null>(null)
  const [warnings, setWarnings] = useState<WarningList | null>(null)
  const [audit, setAudit] = useState<AuditResult | null>(null)
  const [bAdjustments, setBAdjustments] = useState<BAdjustRow[]>([])
  const [adjustValues, setAdjustValues] = useState<Record<string, string>>({})
  const [rendering, setRendering] = useState(false)
  const [renderProgress, setRenderProgress] = useState<number>(0)
  const [busy, setBusy] = useState(false)

  const eid = currentEnterprise?.id ?? ''
  const pid = currentProject?.id ?? ''
  const parseStatus = status?.parse_status ?? ''

  const loadPlan = useCallback(async () => {
    if (!eid || !pid) return
    try {
      const data = await getRenderPlan(eid, pid)
      setPlan(data)
      // 提取 B 类需人工调整的占位符
      const rows: BAdjustRow[] = []
      for (const item of data.plan) {
        for (const ph of item.placeholders) {
          if (ph.type === 'b_class' && ph.needs_manual) {
            rows.push({
              chapter: item.chapter,
              placeholder: ph.name,
              description: ph.description,
              value: ph.value ?? '',
              needs_manual: ph.needs_manual,
            })
          }
        }
      }
      setBAdjustments(rows)
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    }
  }, [eid, pid])

  const loadStatus = useCallback(async () => {
    if (!eid || !pid) return
    try {
      const data = await getRenderStatus(eid, pid)
      setStatus(data)
      setParseStatus(data.parse_status)
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    }
  }, [eid, pid, setParseStatus])

  const loadWarnings = useCallback(async () => {
    if (!eid || !pid) return
    try {
      const data = await getWarnings(eid, pid)
      setWarnings(data)
    } catch {
      /* ignore */
    }
  }, [eid, pid])

  const loadAudit = useCallback(async () => {
    if (!eid || !pid) return
    try {
      const data = await getAuditResult(eid, pid)
      setAudit(data)
    } catch {
      /* ignore */
    }
  }, [eid, pid])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadPlan()
    void loadStatus()
  }, [loadPlan, loadStatus])

  // 渲染完成后自动加载警告和审计
  useEffect(() => {
    if (parseStatus === 'RENDERED') {
      setTimeout(() => {
        void loadWarnings()
        void loadAudit()
      }, 0)
    }
  }, [parseStatus, loadWarnings, loadAudit])

  const handleConfirm = async () => {
    setBusy(true)
    try {
      const adjustments: BClassAdjustment[] = bAdjustments.map((row) => ({
        placeholder: row.placeholder,
        value: adjustValues[row.placeholder] ?? row.value,
      }))
      const res = await confirmRenderPlan(eid, pid, adjustments)
      message.success(
        `渲染计划已确认：${res.total_placeholders} 项占位，${res.b_class_needs_manual} 项 B 类待人工，${res.missing_count} 项缺失`,
      )
      await loadStatus()
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleStartRender = async () => {
    setRendering(true)
    setRenderProgress(0)
    try {
      const onProgress = (event: RenderProgressEvent) => {
        if (event.type === 'progress' && event.event === 'started') {
          setRenderProgress(5)
        }
        if (event.type === 'error') {
          message.error(event.message ?? '渲染失败')
          setRendering(false)
        }
        if (
          event.type === 'progress' &&
          (event.event === 'completed' || event.event === 'cancelled')
        ) {
          setRenderProgress(100)
          setRendering(false)
          loadStatus()
          loadWarnings()
          loadAudit()
        }
      }
      await startRender(eid, pid, onProgress)
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
      setRendering(false)
    }
  }

  const handleCancel = async () => {
    try {
      await cancelRender(eid, pid)
      message.info('已发送取消信号')
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    }
  }

  const handleDownload = (chapter: string) => {
    const url = downloadChapter(eid, pid, chapter)
    window.open(url, '_blank')
  }

  const bColumns: ColumnsType<BAdjustRow> = [
    { title: '章节', dataIndex: 'chapter', key: 'chapter', width: 160, ellipsis: true },
    { title: '占位名', dataIndex: 'placeholder', key: 'placeholder', width: 200 },
    { title: '描述', dataIndex: 'description', key: 'description', width: 180 },
    {
      title: '取值（可人工调整）',
      key: 'value',
      render: (_v, row) => (
        <Search
          defaultValue={adjustValues[row.placeholder] ?? row.value}
          placeholder="OCR 提取值或人工填写"
          allowClear
          onChange={(e) =>
            setAdjustValues((prev) => ({ ...prev, [row.placeholder]: e.target.value }))
          }
          style={{ width: 240 }}
        />
      ),
    },
  ]

  const warningColumns: ColumnsType<{
    chapter: string
    placeholder: string
    problem_type: string
    suggestion: string
  }> = [
    { title: '章节', dataIndex: 'chapter', key: 'chapter', width: 160, ellipsis: true },
    { title: '占位', dataIndex: 'placeholder', key: 'placeholder', width: 200 },
    {
      title: '问题类型',
      dataIndex: 'problem_type',
      key: 'problem_type',
      width: 140,
      render: (v: string) => (
        <Tag
          color={v === 'missing_image' ? 'orange' : v === 'b_class_uncertain' ? 'red' : 'default'}
        >
          {v === 'missing_text' ? '文字缺失' : v === 'missing_image' ? '图片缺失' : 'B类不确定'}
        </Tag>
      ),
    },
    { title: '建议', dataIndex: 'suggestion', key: 'suggestion' },
  ]

  if (!eid || !pid) {
    return (
      <Card>
        <Text>请先选择企业和项目后再进入渲染环节。</Text>
        <Button type="primary" style={{ marginLeft: 12 }} onClick={() => navigate('/workspace')}>
          前往企业/项目
        </Button>
      </Card>
    )
  }

  const showPlan = parseStatus in ['TEMPLATE_REVIEW', 'READY_TO_RENDER', 'RENDERING', 'RENDERED']
  const canConfirm = parseStatus === 'READY_TO_RENDER' || parseStatus === 'RENDERED'
  const canStart = parseStatus === 'READY_TO_RENDER'
  const rendered = parseStatus === 'RENDERED'

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Title level={4} style={{ margin: 0 }}>
        逐章渲染
      </Title>

      {/* 状态摘要 */}
      <Card size="small">
        <Descriptions size="small" column={3}>
          <Descriptions.Item label="解析状态">
            <Tag color={rendered ? 'success' : 'blue'}>{parseStatus || '未知'}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="总章节数">{plan?.total ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="渲染中">
            {rendering ? <Tag color="processing">进行中</Tag> : <Tag>未开始</Tag>}
          </Descriptions.Item>
          {rendering && (
            <Descriptions.Item label="进度" span={3}>
              <Progress percent={renderProgress} status="active" />
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      {/* 渲染计划 */}
      {showPlan && plan && (
        <Tabs
          defaultActiveKey="plan"
          items={[
            {
              key: 'plan',
              label: '渲染计划',
              children: (
                <Card size="small">
                  <Table<RenderPlanItem>
                    rowKey="chapter"
                    size="small"
                    pagination={false}
                    dataSource={plan.plan}
                    columns={[
                      { title: '序号', dataIndex: 'seq', key: 'seq', width: 60 },
                      { title: '章节名', dataIndex: 'chapter', key: 'chapter' },
                      {
                        title: '占位数',
                        key: 'ph_count',
                        width: 80,
                        render: (_v, row) => row.placeholders.length,
                      },
                      {
                        title: '缺失',
                        key: 'missing',
                        width: 80,
                        render: (_v, row) =>
                          row.missing_count > 0 ? (
                            <Tag color="warning">{row.missing_count} 项</Tag>
                          ) : (
                            <Tag color="success">无</Tag>
                          ),
                      },
                    ]}
                  />
                </Card>
              ),
            },
            {
              key: 'b_adjust',
              label: `B 类取值调整（${bAdjustments.length}）`,
              children: (
                <Card size="small">
                  {bAdjustments.length === 0 ? (
                    <Empty description="无 B 类占位需人工调整" />
                  ) : (
                    <Table<BAdjustRow>
                      rowKey={(r) => `${r.chapter}:${r.placeholder}`}
                      size="small"
                      pagination={false}
                      dataSource={bAdjustments}
                      columns={bColumns}
                    />
                  )}
                  <Space style={{ marginTop: 12 }}>
                    <Button
                      type="primary"
                      loading={busy}
                      disabled={!canConfirm}
                      onClick={() => void handleConfirm()}
                    >
                      确认渲染计划
                    </Button>
                  </Space>
                </Card>
              ),
            },
            {
              key: 'warnings',
              label: `警告清单${warnings ? `（${warnings.total}）` : ''}`,
              children: (
                <Card size="small">
                  {warnings && warnings.warnings.length > 0 ? (
                    <Table
                      rowKey={(w) => `${w.chapter}:${w.placeholder}`}
                      size="small"
                      pagination={false}
                      dataSource={warnings.warnings}
                      columns={warningColumns}
                    />
                  ) : (
                    <Alert
                      type="success"
                      showIcon
                      message="无警告"
                      description="渲染结果无缺失或不确定项"
                    />
                  )}
                </Card>
              ),
            },
            {
              key: 'audit',
              label: '一致性审计',
              children: (
                <Card size="small">
                  {audit ? (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Alert
                        type={
                          audit.term_issues.length + audit.consistency_issues.length > 0
                            ? 'warning'
                            : 'success'
                        }
                        showIcon
                        message={audit.summary}
                      />
                      {audit.term_issues.length > 0 && (
                        <div>
                          <Text strong>术语问题</Text>
                          <Table
                            rowKey={(t) => `${t.chapter}:${t.term}`}
                            size="small"
                            pagination={false}
                            dataSource={audit.term_issues}
                            columns={[
                              { title: '章节', dataIndex: 'chapter', key: 'chapter' },
                              { title: '术语', dataIndex: 'term', key: 'term' },
                              { title: '次数', dataIndex: 'count', key: 'count', width: 60 },
                              { title: '预期', dataIndex: 'expected', key: 'expected' },
                            ]}
                          />
                        </div>
                      )}
                      {audit.consistency_issues.length > 0 && (
                        <div>
                          <Text strong>一致性检查</Text>
                          <Table
                            rowKey={(i) => i.field}
                            size="small"
                            pagination={false}
                            dataSource={audit.consistency_issues}
                            columns={[
                              { title: '字段', dataIndex: 'field', key: 'field' },
                              { title: '描述', dataIndex: 'description', key: 'description' },
                              { title: '问题', dataIndex: 'problem', key: 'problem' },
                            ]}
                          />
                        </div>
                      )}
                    </Space>
                  ) : (
                    <Empty description="尚未执行审计" />
                  )}
                </Card>
              ),
            },
          ]}
        />
      )}

      {/* 渲染控制区 */}
      {(canStart || rendering || rendered) && (
        <Card
          size="small"
          title="渲染控制"
          extra={
            <Space>
              {rendered && (
                <Popconfirm
                  title="重新渲染将覆盖已有产物，确认？"
                  onConfirm={() => void handleStartRender()}
                >
                  <Button loading={busy}>重新渲染</Button>
                </Popconfirm>
              )}
              {rendering && (
                <Button danger onClick={() => void handleCancel()}>
                  取消渲染
                </Button>
              )}
            </Space>
          }
        >
          {canStart && !rendering && (
            <Alert
              type="info"
              showIcon
              message="准备就绪（READY_TO_RENDER）"
              description="确认渲染计划后点击「启动渲染」；B 类多候选占位已拦截，可在上方 Tab 中人工指定取值。"
              action={
                <Button type="primary" loading={busy} onClick={() => void handleStartRender()}>
                  启动渲染
                </Button>
              }
            />
          )}
          {rendering && (
            <Alert
              type="processing"
              showIcon
              message={`渲染进行中…当前章节：${status?.current_chapter ?? '-'}`}
              description="可点击「取消渲染」中止；取消后回退到 READY_TO_RENDER 状态。"
            />
          )}
          {rendered && !rendering && (
            <Alert
              type="success"
              showIcon
              message="渲染完成（RENDERED）"
              description="各章节 Word 文件已生成，可在警告清单和审计结果 Tab 中查看质量问题。"
              action={<Button onClick={() => navigate('/template-match')}>返回模板匹配</Button>}
            />
          )}
        </Card>
      )}

      {/* 下载区 */}
      {rendered && plan && (
        <Card size="small" title="下载渲染产物">
          <Space wrap size="middle">
            {plan.plan.map((item) => (
              <Button
                key={item.chapter}
                size="small"
                onClick={() => handleDownload(item.chapter)}
                disabled={false}
              >
                {item.chapter}
              </Button>
            ))}
          </Space>
        </Card>
      )}
    </Space>
  )
}
