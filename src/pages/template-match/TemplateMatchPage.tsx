/**
 * Task 18：模板匹配与语义比对页。
 *
 * 流程（MATERIAL_CONFIRMED 之后）：
 *  1. 进入模板匹配（MATERIAL_CONFIRMED → TEMPLATE_MATCHED）
 *  2. 自动匹配企业模板库（相似度 ≥90% 命中）或手动指定模板文件集（可多选组合）
 *  3. 复制模板到项目 template-work/（版本绑定）→ 执行比对（Schema 门禁 + 机械检查前置 + 语义 diff）
 *  4. 差异 finding 裁决：高置信批量确认、低置信逐条、冲突永不自动应用
 *  5. 全部裁决完成后进入 READY_TO_RENDER
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Badge,
  Button,
  Card,
  Descriptions,
  Empty,
  message,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  autoMatchTemplates,
  batchConfirmFindings,
  confirmTemplateReview,
  copyTemplatesToWork,
  enterTemplateMatching,
  enterTemplateReview,
  getTemplateMatchStatus,
  resolveFinding,
  runTemplateCompare,
  type AutoMatchResult,
  type CompareStatus,
  type Finding,
  type MatchCandidate,
} from '../../api/templateMatch'
import { listTemplates, type TemplateOut } from '../../api/templates'
import { useAppStore } from '../../stores/useAppStore'

const { Text, Title } = Typography

/** 差异动作的中文标签 */
const ACTION_LABELS: Record<string, string> = {
  update: '按解析内容更新（细微差异）',
  replace: '整份用解析内容更新（须披露）',
  keep: '保留模板（拒绝更新）',
  manual_review: '人工复核（冲突/无法判断）',
}

const ACTION_COLORS: Record<string, string> = {
  update: 'blue',
  replace: 'orange',
  keep: 'default',
  manual_review: 'red',
}

const FINDING_TYPE_LABELS: Record<string, string> = {
  paragraph: '段落差异',
  table: '表格差异',
  mechanical: '机械检查',
  unmatched: '关联失败',
}

export default function TemplateMatchPage() {
  const currentEnterprise = useAppStore((s) => s.currentEnterprise)
  const currentProject = useAppStore((s) => s.currentProject)
  const setParseStatus = useAppStore((s) => s.setParseStatus)
  const navigate = useNavigate()

  const [status, setStatus] = useState<CompareStatus | null>(null)
  const [autoResult, setAutoResult] = useState<AutoMatchResult | null>(null)
  const [templates, setTemplates] = useState<TemplateOut[]>([])
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<string[]>([])
  const [rows, setRows] = useState<Finding[]>([])
  const [selectedFindingIds, setSelectedFindingIds] = useState<string[]>([])
  const [batchAction, setBatchAction] = useState<'update' | 'replace' | 'keep'>('update')
  const [busy, setBusy] = useState(false)

  const eid = currentEnterprise?.id ?? ''
  const pid = currentProject?.id ?? ''

  const parseStatus = status?.parse_status ?? ''
  const findings = useMemo(() => rows, [rows])
  const allResolved = findings.length > 0 && findings.every((f) => !!f.resolved_action)
  const highConfidenceIds = useMemo(
    () => findings.filter((f) => f.confidence === 'high' && !f.resolved_action).map((f) => f.id),
    [findings],
  )

  const loadStatus = useCallback(async () => {
    if (!eid || !pid) return
    try {
      const data = await getTemplateMatchStatus(eid, pid)
      setStatus(data)
      setRows(data.findings ?? [])
      setParseStatus(data.parse_status)
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    }
  }, [eid, pid, setParseStatus])

  const loadTemplates = useCallback(async () => {
    if (!eid) return
    try {
      const data = await listTemplates(eid)
      setTemplates(data.items)
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    }
  }, [eid])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadStatus()
  }, [loadStatus])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadTemplates()
  }, [loadTemplates])

  const handleEnter = async () => {
    setBusy(true)
    try {
      const res = await enterTemplateMatching(eid, pid)
      message.success('已进入模板匹配阶段（TEMPLATE_MATCHED）')
      setParseStatus(res.parse_status)
      await loadStatus()
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleAutoMatch = async () => {
    setBusy(true)
    try {
      const res = await autoMatchTemplates(eid, pid)
      setAutoResult(res)
      if (res.error) {
        message.warning(res.error)
      } else if (res.has_match && res.best_match) {
        setSelectedTemplateIds([res.best_match.template_id])
        message.success(`已命中模板：${res.best_match.template_name}（${res.best_match.score} 分）`)
      } else {
        message.warning('未找到相似度 ≥90% 的模板，请人工自选或向模板库补充模板后重新匹配')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleCopy = async () => {
    if (selectedTemplateIds.length === 0) return
    setBusy(true)
    try {
      const res = await copyTemplatesToWork(eid, pid, selectedTemplateIds)
      message.success(`已复制 ${res.copied.length} 个模板文件集到 template-work/`)
      await loadStatus()
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleRunCompare = async () => {
    setBusy(true)
    try {
      const res = await runTemplateCompare(eid, pid)
      message.success(`比对完成：${res.findings_count} 项差异，${res.unmatched_count} 项未匹配`)
      setRows(res.findings)
      await loadStatus()
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleReview = async () => {
    setBusy(true)
    try {
      const res = await enterTemplateReview(eid, pid)
      message.success('已进入差异确认阶段（TEMPLATE_REVIEW）')
      setParseStatus(res.parse_status)
      await loadStatus()
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleConfirm = async () => {
    setBusy(true)
    try {
      const res = await confirmTemplateReview(eid, pid)
      message.success('全部差异已裁决，进入渲染准备（READY_TO_RENDER）')
      setParseStatus(res.parse_status)
      await loadStatus()
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleResolve = async (findingId: string, action: Finding['suggested_action']) => {
    setBusy(true)
    try {
      await resolveFinding(
        eid,
        pid,
        findingId,
        action as 'update' | 'replace' | 'manual_review' | 'keep',
      )
      await loadStatus()
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleBatchConfirm = async () => {
    if (selectedFindingIds.length === 0) return
    setBusy(true)
    try {
      await batchConfirmFindings(eid, pid, selectedFindingIds, batchAction)
      message.success(`已批量裁决 ${selectedFindingIds.length} 项差异`)
      setSelectedFindingIds([])
      await loadStatus()
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const candidateColumns: ColumnsType<MatchCandidate> = [
    { title: '模板名称', dataIndex: 'template_name', key: 'template_name' },
    { title: '代理机构', dataIndex: 'agency', key: 'agency' },
    { title: '类型', dataIndex: 'doc_type', key: 'doc_type' },
    { title: '版本', dataIndex: 'version', key: 'version', render: (v) => `v${v}` },
    {
      title: '相似度',
      dataIndex: 'score',
      key: 'score',
      render: (v: number) =>
        v >= (autoResult?.threshold ?? 90) ? <Tag color="success">{v} 分</Tag> : <Tag>{v} 分</Tag>,
    },
  ]

  const templateColumns: ColumnsType<TemplateOut> = [
    { title: '模板名称', dataIndex: 'name', key: 'name' },
    { title: '代理机构', dataIndex: 'agency', key: 'agency' },
    { title: '类型', dataIndex: 'doc_type', key: 'doc_type' },
    { title: '版本', dataIndex: 'version', key: 'version', render: (v: number) => `v${v}` },
    {
      title: '章节',
      dataIndex: ['meta', 'chapters'],
      key: 'chapters',
      render: (chapters: string[]) => <Text type="secondary">{chapters?.length ?? 0} 章</Text>,
    },
  ]

  const findingColumns: ColumnsType<Finding> = [
    { title: '章节', dataIndex: 'chapter_key', key: 'chapter_key', width: 160, ellipsis: true },
    {
      title: '类型',
      dataIndex: 'finding_type',
      key: 'finding_type',
      width: 100,
      render: (v: string, f) => (
        <Space size={4}>
          <Tag>{FINDING_TYPE_LABELS[v] ?? v}</Tag>
          {f.is_mechanical_red_flag && <Badge status="error" text="标红" />}
        </Space>
      ),
    },
    { title: '差异摘要', dataIndex: 'diff_summary', key: 'diff_summary' },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 90,
      render: (v: string) =>
        v === 'high' ? <Tag color="green">高</Tag> : <Tag color="orange">低</Tag>,
    },
    {
      title: '建议动作',
      dataIndex: 'suggested_action',
      key: 'suggested_action',
      width: 200,
      render: (v: string, f) => (
        <Space size={4}>
          <Tag color={ACTION_COLORS[v] ?? 'default'}>{ACTION_LABELS[v] ?? v}</Tag>
          {f.requires_disclosure && <Tag color="volcano">须披露</Tag>}
        </Space>
      ),
    },
    {
      title: '裁决',
      key: 'resolve',
      width: 220,
      render: (_v, f) => (
        <Select
          size="small"
          style={{ width: 200 }}
          value={f.resolved_action ?? undefined}
          placeholder="待裁决"
          onChange={(val) => void handleResolve(f.id, val)}
          options={[
            { value: 'update', label: '按解析更新' },
            { value: 'replace', label: '整份替换（披露）' },
            { value: 'keep', label: '保留模板（拒绝）' },
            { value: 'manual_review', label: '转入人工复核' },
          ]}
        />
      ),
    },
  ]

  if (!eid || !pid) {
    return (
      <Card>
        <Text>请先选择企业和项目后再进入模板匹配流程。</Text>
        <Button type="primary" style={{ marginLeft: 12 }} onClick={() => navigate('/workspace')}>
          前往企业/项目
        </Button>
      </Card>
    )
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Title level={4} style={{ margin: 0 }}>
        模板匹配与语义比对
      </Title>

      {/* 状态摘要 */}
      <Card size="small">
        <Descriptions size="small" column={3}>
          <Descriptions.Item label="解析状态">
            <Tag color="blue">{parseStatus || '未知'}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="比对记录">
            {status?.has_compare ? <Tag color="success">已建立</Tag> : <Tag>未建立</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="相似度">
            {status?.similarity_score != null ? `${status.similarity_score} 分` : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="差异项">
            {status?.findings_count ?? 0} 项（已裁决 {status?.accepted_count ?? 0}，复核{' '}
            {status?.rejected_count ?? 0}）
          </Descriptions.Item>
          <Descriptions.Item label="匹配方式">{status?.match_method ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="准备就绪时间">
            {status?.ready_at ? new Date(status.ready_at).toLocaleString('zh-CN') : '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 步骤 1：进入模板匹配 */}
      {parseStatus === 'MATERIAL_CONFIRMED' && (
        <Card size="small">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Alert
              type="info"
              showIcon
              message="提取清单已确认（MATERIAL_CONFIRMED）"
              description="进入模板匹配：可自动匹配企业模板库，或手动指定一个/多个模板文件集组合。"
            />
            <Button type="primary" loading={busy} onClick={() => void handleEnter()}>
              进入模板匹配
            </Button>
          </Space>
        </Card>
      )}

      {/* 步骤 2：选择模板 */}
      {['TEMPLATE_MATCHED', 'TEMPLATE_REVIEW', 'READY_TO_RENDER'].includes(parseStatus) && (
        <Card
          size="small"
          title="选择模板"
          extra={
            <Space>
              <Button loading={busy} onClick={() => void handleAutoMatch()}>
                自动匹配（相似度 ≥90%）
              </Button>
              <Button
                type="primary"
                loading={busy}
                disabled={selectedTemplateIds.length === 0}
                onClick={() => void handleCopy()}
              >
                复制所选模板到项目（{selectedTemplateIds.length}）
              </Button>
            </Space>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            {autoResult && !autoResult.error && autoResult.candidates.length > 0 && (
              <div>
                <Text strong>自动匹配候选（相似度降序）</Text>
                <Table<MatchCandidate>
                  rowKey="template_id"
                  size="small"
                  pagination={false}
                  dataSource={autoResult.candidates}
                  columns={candidateColumns}
                  rowSelection={{
                    type: 'checkbox',
                    selectedRowKeys: selectedTemplateIds,
                    onChange: (keys) => setSelectedTemplateIds(keys as string[]),
                  }}
                  style={{ marginTop: 8 }}
                />
                {!autoResult.has_match && (
                  <Alert
                    style={{ marginTop: 8 }}
                    type="warning"
                    showIcon
                    message="无匹配结果"
                    description="未找到相似度 ≥90% 的模板：可从下方模板库人工自选，或先向模板库补充模板（模板库）后重新匹配。"
                    action={
                      <Button size="small" onClick={() => navigate('/templates')}>
                        前往模板库
                      </Button>
                    }
                  />
                )}
              </div>
            )}

            <div>
              <Text strong>模板库（手动指定，可多选组合）</Text>
              <Table<TemplateOut>
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={templates}
                columns={templateColumns}
                locale={{ emptyText: <Empty description="本企业模板库暂无模板" /> }}
                rowSelection={{
                  type: 'checkbox',
                  selectedRowKeys: selectedTemplateIds,
                  onChange: (keys) => setSelectedTemplateIds(keys as string[]),
                }}
                style={{ marginTop: 8 }}
              />
            </div>
          </Space>
        </Card>
      )}

      {/* 步骤 3：执行比对 */}
      {['TEMPLATE_MATCHED', 'TEMPLATE_REVIEW', 'READY_TO_RENDER'].includes(parseStatus) && (
        <Card size="small" title="执行比对">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text type="secondary">
              Schema 门禁（BP-3）通过后执行关联 + 机械检查前置（BP-4）+ 语义 diff，全程不调用 LLM。
            </Text>
            <Space>
              <Button loading={busy} onClick={() => void handleRunCompare()}>
                执行比对
              </Button>
              {parseStatus === 'TEMPLATE_MATCHED' && (
                <Button type="primary" loading={busy} onClick={() => void handleReview()}>
                  差异确认（进入 TEMPLATE_REVIEW）
                </Button>
              )}
            </Space>
          </Space>
        </Card>
      )}

      {/* 步骤 4：差异确认 */}
      {['TEMPLATE_REVIEW', 'READY_TO_RENDER'].includes(parseStatus) && (
        <Card
          size="small"
          title={`差异确认（${findings.length} 项）`}
          extra={
            <Space>
              <Select
                size="small"
                value={batchAction}
                style={{ width: 190 }}
                onChange={setBatchAction}
                options={[
                  { value: 'update', label: '按解析更新' },
                  { value: 'replace', label: '整份替换（披露）' },
                  { value: 'keep', label: '保留模板（拒绝）' },
                ]}
              />
              <Button
                loading={busy}
                disabled={selectedFindingIds.length === 0}
                onClick={() => void handleBatchConfirm()}
              >
                批量裁决所选（{selectedFindingIds.length}）
              </Button>
              <Button
                loading={busy}
                disabled={highConfidenceIds.length === 0}
                onClick={() => {
                  setSelectedFindingIds(highConfidenceIds)
                  message.info(
                    `已选中 ${highConfidenceIds.length} 项高置信差异，请选择动作后批量裁决`,
                  )
                }}
              >
                选中全部高置信
              </Button>
            </Space>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            {findings.length === 0 ? (
              <Alert
                type="success"
                showIcon
                message="无差异文件"
                description="模板与解析内容一致（或无差异项），可直接确认进入渲染准备。"
              />
            ) : (
              <Table<Finding>
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={findings}
                columns={findingColumns}
                rowSelection={{
                  selectedRowKeys: selectedFindingIds,
                  onChange: (keys) => setSelectedFindingIds(keys as string[]),
                  getCheckboxProps: (f) => ({ disabled: !!f.resolved_action }),
                }}
              />
            )}

            {parseStatus === 'TEMPLATE_REVIEW' && (
              <Space>
                <Popconfirm
                  title="确认全部差异已裁决？"
                  description="确认后将进入渲染准备（READY_TO_RENDER）；未裁决的差异会阻断确认。"
                  onConfirm={() => void handleConfirm()}
                  disabled={!allResolved}
                >
                  <Button type="primary" loading={busy} disabled={!allResolved}>
                    确认差异，进入渲染准备
                  </Button>
                </Popconfirm>
                {findings.length > 0 && !allResolved && (
                  <Text type="warning">
                    仍有 {findings.filter((f) => !f.resolved_action).length} 项未裁决
                  </Text>
                )}
              </Space>
            )}

            {parseStatus === 'READY_TO_RENDER' && (
              <Alert
                type="success"
                showIcon
                message="差异全部裁决完成（READY_TO_RENDER）"
                description="可进入渲染环节；差异更新仅作用于项目副本，库内模板不变。"
              />
            )}
          </Space>
        </Card>
      )}
    </Space>
  )
}
