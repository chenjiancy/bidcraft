import {
  Button,
  Card,
  Col,
  Drawer,
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
import { DeleteOutlined, EditOutlined, PlusOutlined, FolderOpenOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'
import * as api from '../../api/materials'
import type { Material } from '../../api/materials'
import { useAppStore } from '../../stores/useAppStore'

const { Title, Text } = Typography
const { Option } = Select

const CATEGORIES = [
  { value: 'qualification', label: '资质证书' },
  { value: 'personnel', label: '人员证书' },
  { value: 'performance', label: '业绩合同' },
  { value: 'honor', label: '荣誉奖项' },
  { value: 'finance', label: '财务材料' },
] as const

export default function MaterialsPage() {
  const [materials, setMaterials] = useState<Material[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [category, setCategory] = useState<string | undefined>()
  const [keyword, setKeyword] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<Material | null>(null)
  const [uploadForm] = Form.useForm()
  const [editForm] = Form.useForm()

  const currentEnterprise = useAppStore((s) => s.currentEnterprise)

  const loadMaterials = useCallback(
    async (p = page, cat = category, kw = keyword) => {
      if (!currentEnterprise) return
      setLoading(true)
      try {
        const res = await api.listMaterials(currentEnterprise.id, {
          category: cat,
          keyword: kw || undefined,
          page: p,
          page_size: 20,
        })
        setMaterials(res.items)
        setTotal(res.total)
        setPage(p)
      } catch (err) {
        message.error(`加载素材失败: ${err}`)
      } finally {
        setLoading(false)
      }
    },
    [currentEnterprise, page, category, keyword],
  )

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadMaterials()
  }, [loadMaterials])

  // ========== 上传 ==========

  const handleUpload = async () => {
    if (!currentEnterprise) return
    try {
      const values = await uploadForm.validateFields()
      const files = await window.bid.dialog.openMaterialFiles()
      if (!files.length) return

      const pathIn: api.MaterialPathIn = {
        file_paths: files.map((f) => f.path),
        category: values.category,
        name: values.name || undefined,
        filename: values.filename || undefined,
        valid_until: values.valid_until || null,
      }

      await api.createMaterialFromPath(currentEnterprise.id, pathIn)
      message.success(`已归档 ${files.length} 个素材`)
      setUploadOpen(false)
      uploadForm.resetFields()
      void loadMaterials()
    } catch (err) {
      if (err instanceof Error && err.message.includes('validation')) return
      message.error(`上传失败: ${err}`)
    }
  }

  // ========== 编辑 ==========

  const handleEdit = (m: Material) => {
    setEditing(m)
    editForm.setFieldsValue({ name: m.name, filename: m.filename, valid_until: m.valid_until })
    setEditOpen(true)
  }

  const handleSaveEdit = async () => {
    if (!currentEnterprise || !editing) return
    try {
      const values = await editForm.validateFields()
      await api.updateMaterial(currentEnterprise.id, editing.id, values)
      message.success('已更新')
      setEditOpen(false)
      void loadMaterials()
    } catch (err) {
      if (err instanceof Error && err.message.includes('validation')) return
      message.error(`保存失败: ${err}`)
    }
  }

  // ========== 删除 ==========

  const handleDelete = async (m: Material) => {
    if (!currentEnterprise) return
    try {
      await api.deleteMaterial(currentEnterprise.id, m.id)
      message.success('已移入回收站')
      void loadMaterials()
    } catch (err) {
      message.error(`删除失败: ${err}`)
    }
  }

  // ========== 列定义 ==========

  const columns: ColumnsType<Material> = [
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 90,
      render: (v: string) => {
        const cat = CATEGORIES.find((c) => c.value === v)
        return cat ? <Tag color="blue">{cat.label}</Tag> : <Tag>{v}</Tag>
      },
    },
    { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: '规范文件名',
      dataIndex: 'filename',
      key: 'filename',
      ellipsis: true,
      render: (v: string) => (
        <Text code style={{ fontSize: 11 }}>
          {v}
        </Text>
      ),
    },
    {
      title: '有效期',
      dataIndex: 'valid_until',
      key: 'valid_until',
      width: 100,
      render: (v: string | null) => (v === 'changqi' ? <Tag color="green">长期</Tag> : (v ?? '-')),
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 60,
      render: (v: number) => <Tag>v{v}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Space>
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
            素材库 — {currentEnterprise.name}
          </Title>
        }
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadOpen(true)}>
            上传素材
          </Button>
        }
      >
        {/* 筛选栏 */}
        <Row gutter={[16, 8]} style={{ marginBottom: 16 }}>
          <Col>
            <Select
              allowClear
              placeholder="按分类筛选"
              style={{ width: 140 }}
              value={category}
              onChange={(v) => {
                setCategory(v)
                void loadMaterials(1)
              }}
            >
              {CATEGORIES.map((c) => (
                <Option key={c.value} value={c.value}>
                  {c.label}
                </Option>
              ))}
            </Select>
          </Col>
          <Col>
            <Input.Search
              placeholder="关键字搜索"
              style={{ width: 220 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onSearch={(v) => {
                setKeyword(v)
                void loadMaterials(1)
              }}
            />
          </Col>
        </Row>

        <Table<Material>
          rowKey="id"
          dataSource={materials}
          columns={columns}
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            showSizeChanger: false,
            onChange: (p) => void loadMaterials(p),
          }}
        />
      </Card>

      {/* 上传抽屉 */}
      <Drawer
        title="上传素材"
        placement="right"
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        width={400}
        extra={
          <Button type="primary" icon={<FolderOpenOutlined />} onClick={handleUpload}>
            选择文件并归档
          </Button>
        }
      >
        <Form form={uploadForm} layout="vertical">
          <Form.Item
            name="category"
            label="分类"
            rules={[{ required: true, message: '请选择分类' }]}
          >
            <Select placeholder="选择分类">
              {CATEGORIES.map((c) => (
                <Option key={c.value} value={c.value}>
                  {c.label}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="name" label="素材名称（可选）">
            <Input placeholder="留空则使用文件名" />
          </Form.Item>
          <Form.Item name="filename" label="规范文件名（可选）">
            <Input placeholder="留空自动生成，如：zcs_建司_20240615" />
          </Form.Item>
          <Form.Item name="valid_until" label="有效期">
            <Input placeholder="YYYYMMDD 或留空表示长期" />
          </Form.Item>
        </Form>
        <Text type="secondary" style={{ fontSize: 12 }}>
          支持 PDF / Word / PNG / JPG / BMP / TIFF
        </Text>
      </Drawer>

      {/* 编辑 Modal */}
      <Modal
        title="编辑素材"
        open={editOpen}
        onOk={handleSaveEdit}
        onCancel={() => setEditOpen(false)}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="name" label="名称">
            <Input />
          </Form.Item>
          <Form.Item name="filename" label="规范文件名">
            <Input />
          </Form.Item>
          <Form.Item name="valid_until" label="有效期">
            <Input placeholder="YYYYMMDD 或 changqi" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
