import { DeleteOutlined, EditOutlined, PlusOutlined, RollbackOutlined } from '@ant-design/icons'
import {
  Button,
  Card,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as api from '../../api/enterprise'
import type { Enterprise, Project, RecycleBinItem } from '../../api/enterprise'
import { useAppStore } from '../../stores/useAppStore'

const { Title, Text } = Typography

export default function WorkspacePage() {
  const [enterprises, setEnterprises] = useState<Enterprise[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [entModalOpen, setEntModalOpen] = useState(false)
  const [editingEnt, setEditingEnt] = useState<Enterprise | null>(null)
  const [projModalOpen, setProjModalOpen] = useState(false)
  const [editingProj, setEditingProj] = useState<Project | null>(null)
  const [recycleOpen, setRecycleOpen] = useState(false)
  const [recycleItems, setRecycleItems] = useState<RecycleBinItem[]>([])
  const [entForm] = Form.useForm()
  const [projForm] = Form.useForm()

  const currentEnterprise = useAppStore((s) => s.currentEnterprise)
  const setCurrentEnterprise = useAppStore((s) => s.setCurrentEnterprise)
  const setCurrentProject = useAppStore((s) => s.setCurrentProject)
  const navigate = useNavigate()

  const loadEnterprises = useCallback(async () => {
    try {
      const data = await api.listEnterprises()
      setEnterprises(data)
      if (currentEnterprise && !data.find((e) => e.id === currentEnterprise.id)) {
        setCurrentEnterprise(null)
      }
    } catch (err) {
      message.error(`加载企业失败: ${err}`)
    }
  }, [currentEnterprise, setCurrentEnterprise])

  const loadProjects = useCallback(async (entId: string) => {
    try {
      setProjects(await api.listProjects(entId))
    } catch (err) {
      message.error(`加载项目失败: ${err}`)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    api
      .listEnterprises()
      .then((data) => {
        if (cancelled) return
        setEnterprises(data)
        if (currentEnterprise && !data.find((e) => e.id === currentEnterprise.id)) {
          setCurrentEnterprise(null)
        }
      })
      .catch((err) => {
        if (!cancelled) message.error(`加载企业失败: ${err}`)
      })
    return () => {
      cancelled = true
    }
  }, [currentEnterprise, setCurrentEnterprise])

  useEffect(() => {
    if (!currentEnterprise) return
    let cancelled = false
    api
      .listProjects(currentEnterprise.id)
      .then((data) => {
        if (!cancelled) setProjects(data)
      })
      .catch((err) => {
        if (!cancelled) message.error(`加载项目失败: ${err}`)
      })
    return () => {
      cancelled = true
    }
  }, [currentEnterprise])

  // ========== 企业操作 ==========

  const handleSaveEnterprise = async () => {
    try {
      const values = await entForm.validateFields()
      if (editingEnt) {
        await api.updateEnterprise(editingEnt.id, values)
        message.success('企业已更新')
      } else {
        const ent = await api.createEnterprise(values)
        setCurrentEnterprise({ id: ent.id, name: ent.name, agent: ent.agent })
        message.success('企业已创建')
      }
      setEntModalOpen(false)
      entForm.resetFields()
      void loadEnterprises()
    } catch (err) {
      if (err instanceof Error && err.message.includes('validation')) return
      message.error(`保存失败: ${err}`)
    }
  }

  const handleDeleteEnterprise = async (id: string) => {
    try {
      await api.deleteEnterprise(id)
      if (currentEnterprise?.id === id) setCurrentEnterprise(null)
      message.success('企业已移入回收站')
      void loadEnterprises()
    } catch (err) {
      message.error(`删除失败: ${err}`)
    }
  }

  // ========== 项目操作 ==========

  const handleSaveProject = async () => {
    if (!currentEnterprise) return
    try {
      const values = await projForm.validateFields()
      if (editingProj) {
        await api.updateProject(currentEnterprise.id, editingProj.id, values)
        message.success('项目已更新')
      } else {
        await api.createProject(currentEnterprise.id, values)
        message.success('项目已创建')
      }
      setProjModalOpen(false)
      projForm.resetFields()
      void loadProjects(currentEnterprise.id)
    } catch (err) {
      if (err instanceof Error && err.message.includes('validation')) return
      message.error(`保存失败: ${err}`)
    }
  }

  const handleDeleteProject = async (projectId: string) => {
    if (!currentEnterprise) return
    try {
      await api.deleteProject(currentEnterprise.id, projectId)
      message.success('项目已移入回收站')
      void loadProjects(currentEnterprise.id)
    } catch (err) {
      message.error(`删除失败: ${err}`)
    }
  }

  // ========== 回收站 ==========

  const loadRecycleBin = useCallback(async () => {
    try {
      setRecycleItems(await api.listRecycleBin(currentEnterprise?.id))
    } catch (err) {
      message.error(`加载回收站失败: ${err}`)
    }
  }, [currentEnterprise])

  const handleRestore = async (itemId: string) => {
    try {
      await api.restoreItem(itemId)
      message.success('已恢复')
      void loadRecycleBin()
      void loadEnterprises()
      if (currentEnterprise) void loadProjects(currentEnterprise.id)
    } catch (err) {
      message.error(`恢复失败: ${err}`)
    }
  }

  const handlePurge = async (itemId: string) => {
    try {
      await api.purgeItem(itemId)
      message.success('已彻底删除')
      void loadRecycleBin()
    } catch (err) {
      message.error(`清除失败: ${err}`)
    }
  }

  // ========== Table 列定义 ==========

  const entColumns: ColumnsType<Enterprise> = [
    { title: '企业名称', dataIndex: 'name', key: 'name' },
    { title: '委托代理人', dataIndex: 'agent', key: 'agent' },
    { title: '联系电话', dataIndex: 'phone', key: 'phone' },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingEnt(record)
              entForm.setFieldsValue(record)
              setEntModalOpen(true)
            }}
          />
          <Popconfirm
            title="删除后企业将进入回收站"
            onConfirm={() => handleDeleteEnterprise(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const projColumns: ColumnsType<Project> = [
    { title: '项目名称', dataIndex: 'name', key: 'name' },
    { title: '项目编号', dataIndex: 'code', key: 'code' },
    { title: '委托代理人', dataIndex: 'agent', key: 'agent' },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            type="primary"
            onClick={() => {
              setCurrentProject({ id: record.id, name: record.name, agent: record.agent })
              navigate('/parse')
            }}
          >
            进入项目
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingProj(record)
              projForm.setFieldsValue(record)
              setProjModalOpen(true)
            }}
          />
          <Popconfirm
            title="删除后项目将进入回收站"
            onConfirm={() => handleDeleteProject(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const recycleColumns: ColumnsType<RecycleBinItem> = [
    {
      title: '类型',
      dataIndex: 'item_type',
      key: 'item_type',
      render: (v: string) => (v === 'enterprise' ? <Tag>企业</Tag> : <Tag color="blue">项目</Tag>),
    },
    { title: '关联ID', dataIndex: 'ref_id', key: 'ref_id', ellipsis: true },
    { title: '删除时间', dataIndex: 'deleted_at', key: 'deleted_at', ellipsis: true },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => handleRestore(record.id)}>
            恢复
          </Button>
          <Popconfirm title="彻底删除后不可恢复" onConfirm={() => handlePurge(record.id)}>
            <Button size="small" danger>
              清除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="large">
      {/* 第一步：选择企业 */}
      <Card
        title={
          <Title level={4} style={{ margin: 0 }}>
            企业
          </Title>
        }
        extra={
          <Space>
            <Button
              icon={<PlusOutlined />}
              onClick={() => {
                setEditingEnt(null)
                entForm.resetFields()
                setEntModalOpen(true)
              }}
            >
              新建企业
            </Button>
            <Button
              icon={<RollbackOutlined />}
              onClick={() => {
                setRecycleOpen(true)
                void loadRecycleBin()
              }}
            >
              回收站
            </Button>
          </Space>
        }
      >
        <Table<Enterprise>
          rowKey="id"
          dataSource={enterprises}
          columns={entColumns}
          pagination={false}
          rowSelection={{
            type: 'radio',
            selectedRowKeys: currentEnterprise ? [currentEnterprise.id] : [],
            onChange: (keys) => {
              const ent = enterprises.find((e) => e.id === keys[0])
              if (ent) {
                setCurrentEnterprise({ id: ent.id, name: ent.name, agent: ent.agent })
                setCurrentProject(null)
              }
            },
          }}
          onRow={(record) => ({
            onClick: () => {
              setCurrentEnterprise({ id: record.id, name: record.name, agent: record.agent })
              setCurrentProject(null)
            },
          })}
        />
      </Card>

      {/* 第二步：选择项目（选中企业后才显示） */}
      {currentEnterprise ? (
        <Card
          title={
            <Space>
              <Title level={4} style={{ margin: 0 }}>
                {currentEnterprise.name} 的项目
              </Title>
              <Text type="secondary">代理人: {currentEnterprise.agent}</Text>
            </Space>
          }
          extra={
            <Button
              icon={<PlusOutlined />}
              onClick={() => {
                setEditingProj(null)
                projForm.resetFields()
                setProjModalOpen(true)
              }}
            >
              新建项目
            </Button>
          }
        >
          <Table<Project>
            rowKey="id"
            dataSource={projects}
            columns={projColumns}
            pagination={false}
            onRow={(record) => ({
              onClick: () =>
                setCurrentProject({ id: record.id, name: record.name, agent: record.agent }),
              style: { cursor: 'pointer' },
            })}
          />
        </Card>
      ) : (
        <Card>
          <Text type="secondary">请先选择或创建一个企业，然后管理其项目。</Text>
        </Card>
      )}

      {/* 企业 Modal */}
      <Modal
        title={editingEnt ? '编辑企业' : '新建企业'}
        open={entModalOpen}
        onOk={handleSaveEnterprise}
        onCancel={() => setEntModalOpen(false)}
        destroyOnClose
      >
        <Form form={entForm} layout="vertical">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入企业名称' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="agent"
            label="委托代理人"
            rules={[{ required: true, message: '委托代理人为必填项' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="legal_person" label="法定代表人">
            <Input />
          </Form.Item>
          <Form.Item name="contact" label="联系人">
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="电话">
            <Input />
          </Form.Item>
          <Form.Item name="intro" label="简介">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 项目 Modal */}
      <Modal
        title={editingProj ? '编辑项目' : '新建项目'}
        open={projModalOpen}
        onOk={handleSaveProject}
        onCancel={() => setProjModalOpen(false)}
        destroyOnClose
      >
        <Form form={projForm} layout="vertical">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="code" label="编号">
            <Input />
          </Form.Item>
          <Form.Item name="agent" label="委托代理人">
            <Input placeholder="留空则使用企业代理人" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 回收站 Drawer */}
      <Drawer
        title="回收站"
        placement="bottom"
        open={recycleOpen}
        onClose={() => setRecycleOpen(false)}
        height={420}
      >
        <Table<RecycleBinItem>
          rowKey="id"
          dataSource={recycleItems}
          columns={recycleColumns}
          pagination={false}
        />
      </Drawer>
    </Space>
  )
}
