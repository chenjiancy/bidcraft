/**
 * Task 14：商务标格式清单确认页。
 *
 * 功能：
 * - 展示 manifest 逐章 docx 清单，EXTERNAL 项标注"系统外/不制作"
 * - 逐条确认（待素材提取门禁）
 * - 增：文件路径 / 名称两种模式
 * - 删：仅标记 removed，文件保留可重新加入
 * - 改：条目名称或更换文件（不做正文改写）
 * - 找不到同名 → status=missing 标红，不阻断其他条目
 * - 确认后状态转 FORMAT_CONFIRMED，调用 setFormatStatus 刷新门禁
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button,
  Checkbox,
  Divider,
  Input,
  message as antdMessage,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  addFormatItemName,
  addFormatItemPath,
  confirmFormatList,
  getFormatList,
  removeFormatItem,
  type FormatListItem,
} from '../../api/parse'
import { useAppStore } from '../../stores/useAppStore'

const { Text } = Typography

interface ItemState {
  [key: string]: boolean
}

export default function BidPage() {
  const currentEnterprise = useAppStore((s) => s.currentEnterprise)
  const currentProject = useAppStore((s) => s.currentProject)
  const setFormatStatus = useAppStore((s) => s.setFormatStatus)
  const navigate = useNavigate()

  const [items, setItems] = useState<FormatListItem[]>([])
  const [total, setTotal] = useState(0)
  const [confirmedCount, setConfirmedCount] = useState(0)
  const [missingCount, setMissingCount] = useState(0)
  const [externalCount, setExternalCount] = useState(0)
  const [confirmedAt, setConfirmedAt] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmState, setConfirmState] = useState<ItemState>({})
  const [addNameOpen, setAddNameOpen] = useState(false)
  const [addNameInput, setAddNameInput] = useState('')
  const [editTarget, setEditTarget] = useState<FormatListItem | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editFile, setEditFile] = useState('')

  const eid = currentEnterprise?.id ?? ''
  const pid = currentProject?.id ?? ''

  const loadList = useCallback(async () => {
    if (!eid || !pid) return
    const data = await getFormatList(eid, pid)
    setItems(data.items)
    setTotal(data.total)
    setConfirmedCount(data.confirmed_count)
    setMissingCount(data.missing_count)
    setExternalCount(data.external_count)
    setConfirmedAt(data.confirmed_at ?? null)
    // 恢复已确认态
    const cs: ItemState = {}
    for (const it of data.items) {
      cs[it.key] = it.status === 'confirmed' || it.status === 'added'
    }
    setConfirmState(cs)
  }, [eid, pid])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadList()
  }, [loadList])

  const handleOpenDocx = async (item: FormatListItem) => {
    if (!item.file) return
    try {
      await window.bid.shell.openDocxFile(eid, pid, item.source_stem, item.file)
    } catch {
      antdMessage.error('打开文件失败，文件可能已被删除')
    }
  }

  const toggleConfirm = useCallback((key: string, checked: boolean) => {
    setConfirmState((prev) => ({ ...prev, [key]: checked }))
  }, [])

  const handleAddByName = async () => {
    const name = addNameInput.trim()
    if (!name) return
    setBusy(true)
    try {
      await addFormatItemName(eid, pid, name)
      antdMessage.success(`已添加条目：${name}`)
      setAddNameOpen(false)
      setAddNameInput('')
      await loadList()
    } catch (err) {
      antdMessage.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleAddByPath = async () => {
    const picked = await window.bid.dialog.openBidFiles()
    if (picked.length === 0) return
    const file = picked[0]
    setBusy(true)
    try {
      await addFormatItemPath(eid, pid, file.path, null)
      antdMessage.success(`已添加条目：${file.name}`)
      await loadList()
    } catch (err) {
      antdMessage.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleRemove = async (item: FormatListItem) => {
    setBusy(true)
    try {
      await removeFormatItem(eid, pid, item.key)
      antdMessage.success(`已移除：${item.title}`)
      await loadList()
    } catch (err) {
      antdMessage.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleEditSave = async () => {
    if (!editTarget) return
    setBusy(true)
    try {
      await removeFormatItem(eid, pid, editTarget.key)
      // 重新添加（简化处理：移除 + 新增同名）
      if (editFile.trim()) {
        await addFormatItemPath(eid, pid, editFile.trim(), editTitle || null)
        antdMessage.success(`已更新条目：${editTitle || editTarget.title}`)
      } else {
        await addFormatItemName(eid, pid, editTitle || editTarget.title)
        antdMessage.success(`已更新条目：${editTitle || editTarget.title}`)
      }
      setEditTarget(null)
      await loadList()
    } catch (err) {
      antdMessage.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleConfirm = async () => {
    const payload = items.map((it) => ({ key: it.key, confirmed: confirmState[it.key] ?? false }))
    setBusy(true)
    try {
      await confirmFormatList(eid, pid, payload, null)
      await loadList()
      setFormatStatus('FORMAT_CONFIRMED')
      antdMessage.success('格式清单已确认，素材提取模块已解锁')
    } catch (err) {
      antdMessage.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const allConfirmed = items.length > 0 && items.every((it) => confirmState[it.key] === true)

  const columns: ColumnsType<FormatListItem> = [
    {
      title: '确认',
      key: 'confirm',
      width: 60,
      render: (_v, it) => (
        <Checkbox
          checked={confirmState[it.key] ?? false}
          onChange={(e) => toggleConfirm(it.key, e.target.checked)}
        />
      ),
    },
    {
      title: '序号',
      key: 'seq',
      width: 50,
      render: (_v, it) => it.seq.toString().padStart(2, '0'),
    },
    {
      title: '章节名称',
      key: 'title',
      render: (_v, it) => (
        <Space>
          <Text strong>{it.title}</Text>
          {it.is_external && <Tag color="default">系统外/不制作</Tag>}
          {it.status === 'missing' && <Tag color="error">MISSING</Tag>}
          {it.status === 'added' && <Tag color="blue">新增</Tag>}
        </Space>
      ),
    },
    {
      title: '文件',
      key: 'file',
      render: (_v, it) => {
        if (!it.file) return <Text type="secondary">-</Text>
        return (
          <Button
            type="link"
            size="small"
            disabled={it.status === 'missing'}
            onClick={() => void handleOpenDocx(it)}
          >
            {it.file}
          </Button>
        )
      },
    },
    {
      title: '来源',
      key: 'source',
      dataIndex: 'source_stem',
      render: (v) => (v ? <Text type="secondary">{v}</Text> : <Text type="secondary">-</Text>),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_v, it) => (
        <Space>
          {it.status !== 'removed' && (
            <>
              <Button
                type="link"
                size="small"
                disabled={it.status === 'missing'}
                onClick={() => {
                  setEditTarget(it)
                  setEditTitle(it.title)
                  setEditFile(it.added_file ?? it.file ?? '')
                }}
              >
                编辑
              </Button>
              <Popconfirm
                title="移出制作范围（文件保留）"
                description="移出后仍可重新加入"
                onConfirm={() => void handleRemove(it)}
                okText="移除"
                cancelText="取消"
              >
                <Button type="link" size="small" danger onClick={() => void handleRemove(it)}>
                  移除
                </Button>
              </Popconfirm>
            </>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size="middle" className="w-full">
      {/* 头部摘要 */}
      <Space wrap>
        <Text strong>商务标格式清单确认</Text>
        <Text type="secondary">
          共 {total} 条（已确认 {confirmedCount}，缺失 {missingCount}，系统外 {externalCount}）
        </Text>
        {confirmedAt && (
          <Tag color="success">已确认于 {new Date(confirmedAt).toLocaleString('zh-CN')}</Tag>
        )}
        {!confirmedAt && <Tag color="warning">待确认 — 未全确认将阻断素材提取</Tag>}
      </Space>

      {/* 操作按钮 */}
      <Space>
        <Button onClick={() => void handleAddByPath()}>+ 添加文件</Button>
        <Button onClick={() => setAddNameOpen(true)}>+ 按名称添加</Button>
        {confirmedAt && (
          <Button type="primary" onClick={() => void navigate('/parse')}>
            返回解析页
          </Button>
        )}
      </Space>

      {/* 清单表格 */}
      <Table
        dataSource={items}
        columns={columns}
        rowKey="key"
        pagination={false}
        size="small"
        locale={{ emptyText: '暂无格式清单条目，请先完成招标文件解析' }}
      />

      {/* 确认按钮 */}
      {!confirmedAt && (
        <Space>
          <Button
            type="primary"
            size="large"
            onClick={() => void handleConfirm()}
            disabled={!allConfirmed || busy}
            loading={busy}
          >
            全部确认并解锁素材提取
          </Button>
          {items.length > 0 && !allConfirmed && <Text type="warning">请确认全部条目后再提交</Text>}
        </Space>
      )}

      {/* 按名称添加弹窗 */}
      <Modal
        title="按名称添加条目"
        open={addNameOpen}
        onCancel={() => {
          setAddNameOpen(false)
          setAddNameInput('')
        }}
        footer={
          <Space>
            <Button disabled={busy} onClick={() => setAddNameOpen(false)}>
              取消
            </Button>
            <Button
              type="primary"
              loading={busy}
              disabled={!addNameInput.trim()}
              onClick={() => void handleAddByName()}
            >
              添加
            </Button>
          </Space>
        }
      >
        <Text type="secondary">输入章节名称，系统将在解析产物和原招标文件中自动查找。</Text>
        <Divider />
        <Input
          value={addNameInput}
          onChange={(e) => setAddNameInput(e.target.value)}
          placeholder="例如：投标函、法定代表人授权书"
          onPressEnter={handleAddByName}
        />
      </Modal>

      {/* 编辑弹窗 */}
      <Modal
        title="编辑条目"
        open={!!editTarget}
        onCancel={() => setEditTarget(null)}
        footer={
          <Space>
            <Button disabled={busy} onClick={() => setEditTarget(null)}>
              取消
            </Button>
            <Button
              type="primary"
              loading={busy}
              disabled={!editTitle.trim()}
              onClick={() => void handleEditSave()}
            >
              保存
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text strong>章节名称</Text>
            <Input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              style={{ marginTop: 4 }}
            />
          </div>
          <div>
            <Text strong>文件路径（可选，留空则按名称重新查找）</Text>
            <Input
              value={editFile}
              onChange={(e) => setEditFile(e.target.value)}
              placeholder="本机绝对路径，支持 .docx / .doc / .pdf"
              style={{ marginTop: 4 }}
            />
            <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
              留空将在解析产物与原招标文件中按名称自动查找；填写路径将直接复制到项目目录。
            </Text>
          </div>
        </Space>
      </Modal>
    </Space>
  )
}
