import {
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  FolderOpenOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'
import * as api from '../../api/templates'
import type { TemplateOut, TemplateUpdateIn, TemplateNewVersionIn } from '../../api/templates'
import { useAppStore } from '../../stores/useAppStore'

const { Title, Text } = Typography
const { Option } = Select

const DOC_TYPE_LABELS: Record<string, string> = {
  bid: '招标',
  procurement: '采购',
  quotation: '询比价',
}

const DOC_TYPE_COLORS: Record<string, string> = {
  bid: 'blue',
  procurement: 'green',
  quotation: 'orange',
}

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<TemplateOut[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [docType, setDocType] = useState<string | undefined>()
  const [nameFilter, setNameFilter] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [newVerOpen, setNewVerOpen] = useState(false)
  const [editing, setEditing] = useState<TemplateOut | null>(null)
  const [latestVer, setLatestVer] = useState<TemplateOut | null>(null)
  const [uploadForm] = Form.useForm()
  const [editForm] = Form.useForm()
  const [newVerForm] = Form.useForm()
  const [complianceOpen, setComplianceOpen] = useState(false)
  const [complianceResult, setComplianceResult] = useState<{
    ok: boolean
    issues: string[]
    phs: string[]
  } | null>(null)
  const [busy, setBusy] = useState(false)

  const currentEnterprise = useAppStore((s) => s.currentEnterprise)

  const loadTemplates = useCallback(
    async (p = page) => {
      if (!currentEnterprise) return
      setLoading(true)
      try {
        const res = await api.listTemplates(currentEnterprise.id, {
          agency: agency || undefined,
          doc_type: docType || undefined,
          name: nameFilter || undefined,
        })
        setTemplates(res.items)
        setTotal(res.total)
        setPage(p)
      } catch (err) {
        message.error(`加载模板失败: ${err}`)
      } finally {
        setLoading(false)
      }
    },
    [currentEnterprise, page, docType, nameFilter],
  )

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadTemplates()
  }, [loadTemplates])

  // TR-17.11: 软件外写入检测
  useEffect(() => {
    if (!currentEnterprise) return
    api
      .checkExternalWrite(currentEnterprise.id)
      .then((res) => {
        if (res.count > 0) {
          message.warning(`检测到 ${res.count} 个模板文件被软件外修改，请在合规检查后重新上传。`)
        }
      })
      .catch(() => {})
  }, [currentEnterprise])

  // ========== 上传新模板 ==========

  const handleUpload = async () => {
    if (!currentEnterprise || !uploadForm) return
    try {
      const values = await uploadForm.validateFields()
      const files = await window.bid.dialog.openBidFiles()
      if (files.length === 0) return
      setBusy(true)
      const in_: api.TemplateCreateIn = {
        agency: values.agency,
        doc_type: values.doc_type,
        name: values.name,
        file_paths: files.map((f) => f.path),
        image_max_width_cm: values.image_max_width_cm || null,
        image_max_height_cm: values.image_max_height_cm || null,
        note: values.note || '',
      }
      await api.createTemplateFromPath(currentEnterprise.id, in_)
      message.success('模板上传成功')
      setUploadOpen(false)
      uploadForm.resetFields()
      void loadTemplates(1)
    } catch (err) {
      if (err instanceof Error && err.message.includes('validation')) return
      message.error(`上传失败: ${err}`)
    } finally {
      setBusy(false)
    }
  }

  // ========== 编辑属性 ==========

  const handleEdit = (tpl: TemplateOut) => {
    setEditing(tpl)
    editForm.setFieldsValue({
      agency: tpl.agency,
      doc_type: tpl.doc_type,
      name: tpl.name,
      image_max_width_cm: tpl.meta.image_max_width_cm,
      image_max_height_cm: tpl.meta.image_max_height_cm,
      note: tpl.meta.note || '',
    })
    setEditOpen(true)
  }

  const handleSaveEdit = async () => {
    if (!currentEnterprise || !editing) return
    try {
      const values = await editForm.validateFields()
      const patch: TemplateUpdateIn = {}
      if (values.agency !== editing.agency) patch.agency = values.agency
      if (values.doc_type !== editing.doc_type) patch.doc_type = values.doc_type
      if (values.name !== editing.name) patch.name = values.name
      patch.image_max_width_cm = values.image_max_width_cm || null
      patch.image_max_height_cm = values.image_max_height_cm || null
      patch.note = values.note || ''
      await api.updateTemplate(currentEnterprise.id, editing.id, patch)
      message.success('属性已更新')
      setEditOpen(false)
      void loadTemplates()
    } catch (err) {
      if (err instanceof Error && err.message.includes('validation')) return
      message.error(`保存失败: ${err}`)
    }
  }

  // ========== 新建版本 ==========

  const handleNewVer = (tpl: TemplateOut) => {
    setLatestVer(tpl)
    newVerForm.resetFields()
    setNewVerOpen(true)
  }

  const handleSaveNewVer = async () => {
    if (!currentEnterprise || !latestVer) return
    try {
      const values = await newVerForm.validateFields()
      const files = await window.bid.dialog.openBidFiles()
      if (files.length === 0) return
      const in_: TemplateNewVersionIn = {
        file_paths: files.map((f) => f.path),
        change_note: values.change_note,
        note: values.note || '',
      }
      setBusy(true)
      const result = await api.newVersion(currentEnterprise.id, latestVer.id, in_)
      message.success(`已创建新版本 v${result.version}`)
      setNewVerOpen(false)
      void loadTemplates()
    } catch (err) {
      if (err instanceof Error && err.message.includes('validation')) return
      message.error(`新建版本失败: ${err}`)
    } finally {
      setBusy(false)
    }
  }

  // ========== 合规检查 ==========

  const handleCheckCompliance = async (tpl: TemplateOut) => {
    if (!currentEnterprise) return
    try {
      const files = await window.bid.dialog.openBidFiles()
      if (files.length === 0) return
      const res = await api.checkCompliance(currentEnterprise.id, tpl.id, {
        file_paths: files.map((f) => f.path),
        change_note: 'check',
        note: '',
      })
      setComplianceResult({
        ok: res.ok,
        issues: res.issues.map((i) => `[${i.code}] ${i.message}`),
        phs: res.placeholders.map((p) => p.placeholder),
      })
      setComplianceOpen(true)
    } catch (err) {
      message.error(`合规检查失败: ${err}`)
    }
  }

  // ========== 词典注册 ==========

  const handleRegisterDict = async () => {
    if (!currentEnterprise || !complianceResult) return
    try {
      const unreg = complianceResult.phs.filter((p) => !p.startsWith('{%'))
      if (unreg.length === 0) {
        message.info('所有占位符已在词典中登记')
        return
      }
      await api.registerPlaceholders(currentEnterprise.id, unreg)
      message.success(`已自动登记 ${unreg.length} 个占位符到动态词典`)
    } catch (err) {
      message.error(`词典登记失败: ${err}`)
    }
  }

  // ========== 删除 ==========

  const handleDelete = async (tpl: TemplateOut) => {
    if (!currentEnterprise) return
    try {
      await api.deleteTemplate(currentEnterprise.id, tpl.id)
      message.success('已移入回收站')
      void loadTemplates()
    } catch (err) {
      message.error(`删除失败: ${err}`)
    }
  }

  // ========== 列定义 ==========

  const columns: ColumnsType<TemplateOut> = [
    {
      title: '代理机构',
      dataIndex: 'agency',
      key: 'agency',
      width: 140,
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'doc_type',
      key: 'doc_type',
      width: 80,
      render: (v: string) => (
        <Tag color={DOC_TYPE_COLORS[v] ?? 'default'}>{DOC_TYPE_LABELS[v] ?? v}</Tag>
      ),
    },
    { title: '模板名称', dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 70,
      render: (v: number) => <Tag>v{v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: string) => <Tag color={v === 'active' ? 'green' : 'default'}>{v}</Tag>,
    },
    {
      title: '章节数',
      key: 'chapters',
      width: 80,
      render: (_, record) => record.meta?.chapters?.length ?? 0,
    },
    {
      title: '操作',
      key: 'action',
      width: 260,
      render: (_, record) => (
        <Space wrap>
          <Button
            size="small"
            icon={<ThunderboltOutlined />}
            onClick={() => handleCheckCompliance(record)}
          >
            合规检查
          </Button>
          <Button
            size="small"
            icon={<PlusOutlined />}
            onClick={() => handleNewVer(record)}
            disabled={record.referenced}
            title={record.referenced ? '已被引用，只能新建版本' : ''}
          >
            新建版本
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record)}
          />
        </Space>
      ),
    },
  ]

  if (!currentEnterprise) {
    return (
      <Card>
        <Text type="secondary">请先在「企业/项目」中选择或创建一个企业。</Text>
      </Card>
    )
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      <Card
        title={
          <Title level={4} style={{ margin: 0 }}>
            模板库 — {currentEnterprise.name}
          </Title>
        }
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadOpen(true)}>
            上传模板
          </Button>
        }
      >
        {/* 筛选栏 */}
        <Row gutter={[16, 8]} style={{ marginBottom: 16 }}>
          <Col>
            <Input.Search
              placeholder="按模板名称搜索"
              style={{ width: 200 }}
              value={nameFilter}
              onChange={(e) => setNameFilter(e.target.value)}
              onSearch={(v) => {
                setNameFilter(v)
                void loadTemplates(1)
              }}
            />
          </Col>
          <Col>
            <Select
              allowClear
              placeholder="按文件类型筛选"
              style={{ width: 140 }}
              value={docType}
              onChange={(v) => {
                setDocType(v)
                void loadTemplates(1)
              }}
            >
              <Option value="bid">招标</Option>
              <Option value="procurement">采购</Option>
              <Option value="quotation">询比价</Option>
            </Select>
          </Col>
        </Row>

        <Table<TemplateOut>
          rowKey="id"
          dataSource={templates}
          columns={columns}
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            showSizeChanger: false,
            onChange: (p) => void loadTemplates(p),
          }}
        />
      </Card>

      {/* 上传模板抽屉 */}
      <Modal
        title="上传模板"
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        footer={null}
        width={480}
      >
        <Form form={uploadForm} layout="vertical">
          <Form.Item
            name="agency"
            label="代理机构名称"
            rules={[{ required: true, message: '请填写代理机构名称' }]}
          >
            <Input placeholder="如：XX招标代理有限公司" />
          </Form.Item>
          <Form.Item
            name="doc_type"
            label="文件类型"
            rules={[{ required: true, message: '请选择文件类型' }]}
          >
            <Select placeholder="选择文件类型">
              <Option value="bid">招标</Option>
              <Option value="procurement">采购</Option>
              <Option value="quotation">询比价</Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="name"
            label="模板名称"
            rules={[{ required: true, message: '请填写模板名称' }]}
          >
            <Input placeholder="如：某某项目标准招标文件" />
          </Form.Item>
          <Form.Item name="image_max_width_cm" label="图片最大宽度(cm，可选)">
            <Input type="number" placeholder="如：18" />
          </Form.Item>
          <Form.Item name="image_max_height_cm" label="图片最大高度(cm，可选)">
            <Input type="number" placeholder="如：12" />
          </Form.Item>
          <Form.Item name="note" label="备注（可选）">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              icon={<FolderOpenOutlined />}
              loading={busy}
              onClick={handleUpload}
            >
              选择文件并上传
            </Button>
          </Form.Item>
          <Text type="secondary" style={{ fontSize: 12 }}>
            选择 docx 格式的章节文件集（含 template.json 或软件自动生成）
          </Text>
        </Form>
      </Modal>

      {/* 编辑属性 Modal */}
      <Modal
        title="编辑模板属性"
        open={editOpen}
        onOk={handleSaveEdit}
        onCancel={() => setEditOpen(false)}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="agency" label="代理机构名称">
            <Input />
          </Form.Item>
          <Form.Item name="doc_type" label="文件类型">
            <Select>
              <Option value="bid">招标</Option>
              <Option value="procurement">采购</Option>
              <Option value="quotation">询比价</Option>
            </Select>
          </Form.Item>
          <Form.Item name="name" label="模板名称">
            <Input />
          </Form.Item>
          <Form.Item name="image_max_width_cm" label="图片最大宽度(cm)">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="image_max_height_cm" label="图片最大高度(cm)">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 新建版本 Modal */}
      <Modal
        title={`新建版本（当前 v${latestVer?.version}）`}
        open={newVerOpen}
        onOk={handleSaveNewVer}
        onCancel={() => setNewVerOpen(false)}
        confirmLoading={busy}
        destroyOnClose
        width={480}
      >
        <Form form={newVerForm} layout="vertical">
          <Form.Item
            name="change_note"
            label="变更说明（必填）"
            rules={[{ required: true, message: '请填写变更说明' }]}
          >
            <Input.TextArea rows={3} placeholder="描述本次版本变更内容" />
          </Form.Item>
          <Form.Item name="note" label="备注（可选）">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" icon={<FolderOpenOutlined />} loading={busy}>
              选择新文件并创建版本
            </Button>
          </Form.Item>
          {latestVer?.referenced && (
            <Text type="danger">此模板已被标书引用，不允许覆盖，只能新建版本。</Text>
          )}
        </Form>
      </Modal>

      {/* 合规检查结果 Modal */}
      <Modal
        title="合规检查结果"
        open={complianceOpen}
        onCancel={() => setComplianceOpen(false)}
        footer={[
          <Button key="reg" onClick={handleRegisterDict}>
            一键登记未注册占位符
          </Button>,
          <Button key="close" onClick={() => setComplianceOpen(false)}>
            关闭
          </Button>,
        ]}
        width={560}
      >
        {complianceResult && (
          <div>
            <Tag color={complianceResult.ok ? 'green' : 'red'} style={{ marginBottom: 8 }}>
              {complianceResult.ok ? '通过' : '未通过'}
            </Tag>
            {complianceResult.issues.length > 0 && (
              <ul style={{ paddingLeft: 20, margin: '8px 0' }}>
                {complianceResult.issues.map((issue, i) => (
                  <li key={i} style={{ color: '#cf1322', marginBottom: 4 }}>
                    {issue}
                  </li>
                ))}
              </ul>
            )}
            {complianceResult.phs.length > 0 && (
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  占位符示例（前 10 个）：
                </Text>
                <Space wrap style={{ marginTop: 4 }}>
                  {complianceResult.phs.slice(0, 10).map((ph) => (
                    <Tag key={ph} style={{ fontSize: 11 }}>
                      {ph}
                    </Tag>
                  ))}
                </Space>
              </div>
            )}
          </div>
        )}
      </Modal>
    </Space>
  )
}
