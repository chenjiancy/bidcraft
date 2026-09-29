import {
  Alert,
  Button,
  Card,
  Checkbox,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  CheckCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useMemo, useState } from 'react'
import * as api from '../../api/materialExtract'
import type { CandidateGroup, ExtractItem } from '../../api/materialExtract'
import { useAppStore } from '../../stores/useAppStore'

const { Title, Text, Paragraph } = Typography

const CATEGORIES = [
  { value: 'qualification', label: '资质证书' },
  { value: 'personnel', label: '人员证书' },
  { value: 'performance', label: '业绩合同' },
  { value: 'honor', label: '荣誉奖项' },
  { value: 'finance', label: '财务材料' },
] as const

const STATUS_TAG: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '待查' },
  selected: { color: 'green', text: '已选定' },
  missing: { color: 'red', text: '缺失' },
  deferred: { color: 'orange', text: '待定' },
}

export default function MaterialsExtractPage() {
  const currentEnterprise = useAppStore((s) => s.currentEnterprise)
  const currentProject = useAppStore((s) => s.currentProject)
  const isMaterialConfirmed = useAppStore((s) => s.isMaterialConfirmed)
  const setMaterialStatus = useAppStore((s) => s.setMaterialStatus)

  const [items, setItems] = useState<ExtractItem[]>([])
  const [round, setRound] = useState(1)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)

  // 查询候选面板
  const [queryOpen, setQueryOpen] = useState(false)
  const [candidates, setCandidates] = useState<CandidateGroup[]>([])
  const [querying, setQuerying] = useState(false)
  const [checkedGroups, setCheckedGroups] = useState<string[]>([])

  const [addOpen, setAddOpen] = useState(false)
  const [editItem, setEditItem] = useState<ExtractItem | null>(null)
  const [importItem, setImportItem] = useState<ExtractItem | null>(null)
  const [addForm] = Form.useForm()
  const [editForm] = Form.useForm()
  const [importForm] = Form.useForm()

  // 本地草稿：未保存的 status / selected 变化（TR-16.11 定时草稿由后端 checkpoint 承担）
  const [draft, setDraft] = useState<Record<string, { status?: string; materialId?: string }>>({})

  const eid = currentEnterprise?.id
  const pid = currentProject?.id

  const loadList = useCallback(async () => {
    if (!eid || !pid) return
    setLoading(true)
    try {
      const data = await api.getExtractList(eid, pid)
      setItems(data.items)
      setRound(data.items[0]?.round ?? 1)
    } catch (err) {
      message.error(`加载提取清单失败: ${err}`)
    } finally {
      setLoading(false)
    }
  }, [eid, pid])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadList()
  }, [loadList])

  const stats = useMemo(() => {
    let pending = 0
    let selected = 0
    let missing = 0
    for (const item of items) {
      const s = draft[item.id]?.status ?? item.status
      if (s === 'pending') pending += 1
      else if (s === 'selected') selected += 1
      else if (s === 'missing') missing += 1
    }
    return { pending, selected, missing, total: items.length }
  }, [items, draft])

  function effStatus(item: ExtractItem): string {
    return draft[item.id]?.status ?? item.status
  }

  function effMaterial(item: ExtractItem): string | null {
    return draft[item.id]?.materialId ?? item.selected_material_id
  }

  // ---------- 生成清单 ----------

  const handleGenerate = async () => {
    if (!eid || !pid) return
    setBusy(true)
    try {
      const res = await api.generateExtractList(eid, pid, round)
      message.success(`已生成 ${res.requirement_count} 条待查需求`)
      setDraft({})
      await loadList()
    } catch (err) {
      message.error(`生成失败: ${err}`)
    } finally {
      setBusy(false)
    }
  }

  // ---------- 查询匹配 ----------

  const handleQuery = async (item: ExtractItem) => {
    if (!eid || !pid) return
    setSelectedItemId(item.id)
    setQueryOpen(true)
    setQuerying(true)
    setCheckedGroups([])
    try {
      const res = await api.queryCandidates(eid, pid, {
        keyword: item.requirement_name,
      })
      setCandidates(res.candidates)
      // 已选定的素材组默认勾选
      const selectedGroup = res.candidates.find((g) =>
        g.items.some((c) => c.id === effMaterial(item)),
      )
      if (selectedGroup) setCheckedGroups([selectedGroup.group_key])
    } catch (err) {
      message.error(`查询失败: ${err}`)
    } finally {
      setQuerying(false)
    }
  }

  const applyCandidateSelection = () => {
    if (!selectedItemId) return
    const chosen = candidates.filter((g) => checkedGroups.includes(g.group_key))
    const firstId = chosen[0]?.items[0]?.id ?? null
    setDraft((d) => ({
      ...d,
      [selectedItemId]: { status: 'selected', materialId: firstId },
    }))
    setQueryOpen(false)
    message.success('已记录选定（记得保存本轮）')
  }

  const markMissing = (item: ExtractItem) => {
    setDraft((d) => ({ ...d, [item.id]: { status: 'missing' } }))
  }

  const clearConclusion = (item: ExtractItem) => {
    setDraft((d) => ({ ...d, [item.id]: { status: 'pending' } }))
  }

  // ---------- A 类：库外文件导入（查询异常，文件实际存在但不在库内） ----------

  const handleImportExternal = async () => {
    if (!eid || !pid || !importItem) return
    try {
      const values = await importForm.validateFields()
      const picked = await window.bid.dialog.openMaterialFiles()
      if (picked.length === 0) return
      setBusy(true)
      const res = await api.importExternal(eid, pid, {
        file_path: picked[0].path,
        category: values.category,
        name: values.name || undefined,
      })
      setDraft((d) => ({
        ...d,
        [importItem.id]: { status: 'selected', materialId: res.id },
      }))
      message.success('已导入项目素材并选定（记得保存本轮）')
      setImportItem(null)
      importForm.resetFields()
    } catch (err) {
      if (err instanceof Error && err.message.includes('validation')) return
      message.error(`导入失败: ${err}`)
    } finally {
      setBusy(false)
    }
  }

  // ---------- 保存轮次 ----------

  const handleSaveRound = async () => {
    if (!eid || !pid) return
    const changes = Object.entries(draft).map(([item_id, v]) => ({
      item_id,
      status: v.status,
      selected_material_id: v.materialId,
    }))
    if (!changes.length) {
      message.info('没有需要保存的改动')
      return
    }
    setBusy(true)
    try {
      const data = await api.saveRound(eid, pid, { round, changes })
      setItems(data.items)
      setDraft({})
      message.success('本轮结论已保存')
    } catch (err) {
      message.error(`保存失败: ${err}`)
    } finally {
      setBusy(false)
    }
  }

  // ---------- 确认保存清单（门禁） ----------

  const handleConfirm = async () => {
    if (!eid || !pid) return
    setBusy(true)
    try {
      if (Object.keys(draft).length) await handleSaveRound()
      const res = await api.confirmExtractList(eid, pid, round)
      message.success(`提取清单已保存（${res.item_count} 项），进入模板匹配阶段`)
      setMaterialStatus('MATERIAL_CONFIRMED')
      await loadList()
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  // ---------- 开启新一轮 ----------

  const handleNewRound = async () => {
    if (!eid || !pid) return
    setBusy(true)
    try {
      const res = await api.startNewRound(eid, pid)
      message.success(`已开启第 ${res.round} 轮`)
      setDraft({})
      await loadList()
    } catch (err) {
      message.error(`开启新一轮失败: ${err}`)
    } finally {
      setBusy(false)
    }
  }

  // ---------- 增删改需求项 ----------

  const handleAdd = async () => {
    if (!eid || !pid) return
    try {
      const values = await addForm.validateFields()
      await api.addRequirement(eid, pid, values)
      message.success('已新增需求项')
      setAddOpen(false)
      addForm.resetFields()
      await loadList()
    } catch (err) {
      if (err instanceof Error && err.message.includes('validation')) return
      message.error(`新增失败: ${err}`)
    }
  }

  const handleEdit = async () => {
    if (!eid || !pid || !editItem) return
    try {
      const values = await editForm.validateFields()
      await api.updateRequirement(eid, pid, editItem.id, values)
      message.success('已修改')
      setEditItem(null)
      await loadList()
    } catch (err) {
      if (err instanceof Error && err.message.includes('validation')) return
      message.error(`修改失败: ${err}`)
    }
  }

  const handleDelete = async (item: ExtractItem) => {
    if (!eid || !pid) return
    try {
      await api.deleteRequirement(eid, pid, item.id)
      message.success('已删除')
      await loadList()
    } catch (err) {
      message.error(`删除失败: ${err}`)
    }
  }

  // ---------- 列 ----------

  const columns: ColumnsType<ExtractItem> = [
    {
      title: '需求项',
      dataIndex: 'requirement_name',
      key: 'requirement_name',
      ellipsis: true,
      render: (v: string, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{v}</Text>
          {record.source_anchor && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              来源：{record.source === 'score_table' ? '评分办法' : '格式清单'} ·{' '}
              {record.source_anchor}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: (_, record) => {
        const s = effStatus(record)
        const tag = STATUS_TAG[s] ?? { color: 'default', text: s }
        return <Tag color={tag.color}>{tag.text}</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 380,
      render: (_, record) => {
        const s = effStatus(record)
        return (
          <Space size="small" wrap>
            <Button
              size="small"
              type="primary"
              icon={<SearchOutlined />}
              onClick={() => void handleQuery(record)}
            >
              查询匹配
            </Button>
            {s !== 'missing' ? (
              <Tooltip title="库内确实没有此材料">
                <Button size="small" onClick={() => markMissing(record)}>
                  标记缺失
                </Button>
              </Tooltip>
            ) : (
              <Button size="small" onClick={() => clearConclusion(record)}>
                撤销结论
              </Button>
            )}
            <Tooltip title="文件实际存在但不在库内：从本机导入项目素材">
              <Button size="small" onClick={() => setImportItem(record)}>
                库外导入
              </Button>
            </Tooltip>
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => {
                setEditItem(record)
                editForm.setFieldsValue({ requirement_name: record.requirement_name })
              }}
            />
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => void handleDelete(record)}
            />
          </Space>
        )
      },
    },
  ]

  if (!eid || !pid) {
    return (
      <Card>
        <Empty description="请先在「企业/项目」中选择一个项目" />
      </Card>
    )
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      <Card>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Title level={4} style={{ margin: 0 }}>
            素材提取清单 — {currentProject?.name}
          </Title>
          <Steps
            size="small"
            current={isMaterialConfirmed ? 2 : stats.pending > 0 ? 0 : 1}
            items={[
              { title: '聚合待查清单', description: `第 ${round} 轮` },
              {
                title: '查询匹配收敛',
                description: `${stats.selected + stats.missing}/${stats.total} 有结论`,
              },
              { title: '确认保存', description: isMaterialConfirmed ? '已保存' : '未保存' },
            ]}
          />
          <Space wrap>
            <Button
              icon={<PlayCircleOutlined />}
              loading={busy}
              onClick={() => void handleGenerate()}
            >
              生成/重置待查清单
            </Button>
            <Button icon={<ReloadOutlined />} loading={busy} onClick={() => void handleNewRound()}>
              开启新一轮
            </Button>
            <Button icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
              手工新增需求项
            </Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={busy}
              disabled={!Object.keys(draft).length}
              onClick={() => void handleSaveRound()}
            >
              保存本轮结论
            </Button>
            <Button
              type="primary"
              danger
              icon={<CheckCircleOutlined />}
              loading={busy}
              disabled={stats.pending > 0 || stats.total === 0}
              onClick={() => void handleConfirm()}
            >
              确认保存清单
            </Button>
          </Space>
          <Space size="large">
            <Text>共 {stats.total} 项</Text>
            <Text type="secondary">待查 {stats.pending}</Text>
            <Text type="success">已选定 {stats.selected}</Text>
            <Text type="danger">缺失 {stats.missing}</Text>
            {Object.keys(draft).length > 0 && (
              <Tag color="orange">{Object.keys(draft).length} 项未保存</Tag>
            )}
          </Space>
          {isMaterialConfirmed && (
            <Alert
              type="success"
              showIcon
              message="提取清单已确认保存（MATERIAL_CONFIRMED）"
              description="已保存的清单是后续渲染时提取素材的唯一依据；标记为「缺失」的材料将在渲染时占位并进入警告清单。"
            />
          )}
          {!isMaterialConfirmed && stats.pending > 0 && (
            <Alert
              type="warning"
              showIcon
              message={`仍有 ${stats.pending} 项待查`}
              description="每项需有结论（选定素材或确认缺失）后方可保存清单。库内确实没有时，可经「素材库 → 上传素材」补充后重新查询。"
            />
          )}
        </Space>
      </Card>

      <Card title={`需求项清单（第 ${round} 轮）`}>
        <Table<ExtractItem>
          rowKey="id"
          dataSource={items}
          columns={columns}
          loading={loading}
          pagination={false}
          locale={{ emptyText: <Empty description="暂无需求项，请先「生成/重置待查清单」" /> }}
        />
      </Card>

      {/* 查询候选抽屉/Modal */}
      <Modal
        title={
          <Space>
            <span>查询匹配候选</span>
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>
              多页素材已按证件组聚合，勾选整组即可
            </Text>
          </Space>
        }
        open={queryOpen}
        onCancel={() => setQueryOpen(false)}
        onOk={applyCandidateSelection}
        okText="选定并记录"
        okButtonProps={{ disabled: !checkedGroups.length }}
        width={720}
        confirmLoading={querying}
      >
        {candidates.length === 0 ? (
          <Empty
            description={
              <Space direction="vertical">
                <Text>库内未找到匹配素材</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  可经「素材库 → 上传素材」补充归档后，再返回本页重新查询。
                </Text>
              </Space>
            }
          />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }}>
            {candidates.map((group) => (
              <Card
                key={group.group_key}
                size="small"
                title={
                  <Space>
                    <Checkbox
                      checked={checkedGroups.includes(group.group_key)}
                      onChange={(e) => {
                        const on = e.target.checked
                        setCheckedGroups((prev) =>
                          on
                            ? [...prev, group.group_key]
                            : prev.filter((k) => k !== group.group_key),
                        )
                      }}
                    />
                    <Text style={{ fontSize: 12 }}>{group.group_key}</Text>
                    {group.items.length > 1 && <Tag>{group.items.length} 页</Tag>}
                  </Space>
                }
              >
                <Space wrap>
                  {group.items.map((c) => (
                    <Tooltip key={c.id} title={c.file_path}>
                      <Tag color="blue">{c.filename || c.name}</Tag>
                    </Tooltip>
                  ))}
                  {group.items[0]?.valid_until && (
                    <Tag color={group.items[0].valid_until === 'changqi' ? 'green' : 'orange'}>
                      有效期{' '}
                      {group.items[0].valid_until === 'changqi'
                        ? '长期'
                        : group.items[0].valid_until}
                    </Tag>
                  )}
                </Space>
              </Card>
            ))}
            <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
              候选按相似度（BM25）排序；范围仅限本企业共享库 + 本项目独享库。
            </Paragraph>
          </Space>
        )}
      </Modal>

      {/* 新增需求项 */}
      <Modal
        title="新增需求项"
        open={addOpen}
        onOk={handleAdd}
        onCancel={() => setAddOpen(false)}
        destroyOnClose
      >
        <Form form={addForm} layout="vertical">
          <Form.Item
            name="requirement_name"
            label="需求名称"
            rules={[{ required: true, message: '请输入需求名称' }]}
          >
            <Input placeholder="如：监理工程师注册证书" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑需求项 */}
      <Modal
        title="修改需求项"
        open={!!editItem}
        onOk={handleEdit}
        onCancel={() => setEditItem(null)}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="requirement_name"
            label="需求名称"
            rules={[{ required: true, message: '请输入需求名称' }]}
          >
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      {/* A 类：库外文件导入 */}
      <Modal
        title="库外文件导入"
        open={!!importItem}
        onOk={() => void handleImportExternal()}
        onCancel={() => setImportItem(null)}
        okText="选择文件并导入"
        confirmLoading={busy}
        destroyOnClose
      >
        <Paragraph type="secondary" style={{ fontSize: 12 }}>
          用于「文件确实存在但不在库内」的情形：选定类别后从本机选择文件，系统会复制一份到本项目的
          project-materials/ 目录并归档，同时记为该项的选定素材。
        </Paragraph>
        <Form form={importForm} layout="vertical" initialValues={{ category: 'qualification' }}>
          <Form.Item
            name="category"
            label="素材类别"
            rules={[{ required: true, message: '请选择素材类别' }]}
          >
            <Select
              options={CATEGORIES.map((c) => ({ value: c.value, label: c.label }))}
              placeholder="请选择"
            />
          </Form.Item>
          <Form.Item name="name" label="素材名称（可选）">
            <Input placeholder="留空则使用文件名" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
