/**
 * Task 13：解析清单复核组件。
 * 三 Tab：规则粗分 / 评分表 / 投标文件格式。
 * 逐条确认 + 增删 + 标红 + 门禁解锁。
 */
import { useCallback, useMemo, useState } from 'react'
import { Button, Checkbox, Progress, Space, Table, Tabs, Tag, Typography } from 'antd'
import type {
  DocxFile,
  DocxManifest,
  ExtractItem,
  ExtractList,
  ParseConfirmItem,
  ParseConfirmPayload,
  ScoreTable,
} from '../../api/parse'

const { Text } = Typography

export interface ParseChecklistReviewProps {
  extraction: ExtractList | null
  score: ScoreTable | null
  docx: DocxManifest | null
  enterpriseId: string
  projectId: string
  onSave: (payload: ParseConfirmPayload) => Promise<void>
  onCancel: () => void
  saving: boolean
}

interface ConfirmState {
  // key = `${tab}:${item_id}`
  [key: string]: boolean
}

export function ParseChecklistReview({
  extraction,
  score,
  docx,
  enterpriseId,
  projectId,
  onSave,
  onCancel,
  saving,
}: ParseChecklistReviewProps) {
  const [confirmations, setConfirmations] = useState<ConfirmState>({})
  const [activeTab, setActiveTab] = useState('extraction')

  // 收集所有需确认的条目 ID
  const allItems = useMemo(() => {
    const items: Array<{ tab: string; item_id: string; label: string }> = []
    if (extraction) {
      for (const item of extraction.items) {
        if (!item.selected) continue
        if (item.matches.length > 0) {
          item.matches.forEach((_m, i) => {
            items.push({
              tab: 'extraction',
              item_id: `${item.key}:${i}`,
              label: `${item.label} #${i + 1}`,
            })
          })
        } else {
          items.push({ tab: 'extraction', item_id: `${item.key}:0`, label: item.label })
        }
      }
    }
    if (score) {
      score.categories.forEach((cat, ci) => {
        cat.items.forEach((_si, ii) => {
          items.push({
            tab: 'score',
            item_id: `${ci}:${ii}`,
            label: `${cat.name} / ${score.categories[ci].items[ii].name}`,
          })
        })
      })
    }
    if (docx) {
      for (const src of docx.sources) {
        for (const f of src.files) {
          if (f.state === 'success') {
            items.push({
              tab: 'docx',
              item_id: f.checkpoint_key,
              label: `${src.source_stem} / ${f.seq.toString().padStart(2, '0')}_${f.title}.docx`,
            })
          }
        }
      }
    }
    return items
  }, [extraction, score, docx])

  const confirmedCount = useMemo(
    () => allItems.filter((i) => confirmations[`${i.tab}:${i.item_id}`]).length,
    [allItems, confirmations],
  )
  const allConfirmed = confirmedCount === allItems.length && allItems.length > 0

  const toggle = useCallback((tab: string, itemId: string, checked: boolean) => {
    setConfirmations((prev) => ({ ...prev, [`${tab}:${itemId}`]: checked }))
  }, [])

  const handleSave = useCallback(() => {
    const items: ParseConfirmItem[] = allItems.map((i) => ({
      tab: i.tab as ParseConfirmItem['tab'],
      item_id: i.item_id,
      confirmed: confirmations[`${i.tab}:${i.item_id}`] ?? false,
    }))
    onSave({
      items,
      extraction: extraction ?? undefined,
      score: score ?? undefined,
      docx: docx ?? undefined,
    })
  }, [allItems, confirmations, extraction, score, docx, onSave])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <Text strong>
          已确认 {confirmedCount} / {allItems.length} 条
        </Text>
        <Progress
          percent={allItems.length > 0 ? Math.round((confirmedCount / allItems.length) * 100) : 0}
          status={allConfirmed ? 'success' : 'active'}
        />
        {!allConfirmed && <Text type="warning"> 全部条目确认后才能保存解锁</Text>}
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'extraction',
            label: `规则粗分${extraction ? ` (${extraction.items.filter((i) => i.selected).length})` : ''}`,
            children: (
              <ExtractionTab
                extraction={extraction}
                confirmations={confirmations}
                onToggle={toggle}
              />
            ),
          },
          {
            key: 'score',
            label: `评分表${score ? ` (${score.categories.reduce((n, c) => n + c.items.length, 0)})` : ''}`,
            children: <ScoreTab score={score} confirmations={confirmations} onToggle={toggle} />,
          },
          {
            key: 'docx',
            label: `投标文件格式${docx ? ` (${docx.total_files})` : ''}`,
            children: (
              <DocxTab
                docx={docx}
                confirmations={confirmations}
                onToggle={toggle}
                enterpriseId={enterpriseId}
                projectId={projectId}
              />
            ),
          },
        ]}
      />

      <Space>
        <Button
          type="primary"
          onClick={handleSave}
          disabled={!allConfirmed || saving}
          loading={saving}
        >
          保存并解锁
        </Button>
        <Button onClick={onCancel} disabled={saving}>
          取消
        </Button>
      </Space>
    </div>
  )
}

// ---------- Tab 1: 规则粗分 ----------

function ExtractionTab({
  extraction,
  confirmations,
  onToggle,
}: {
  extraction: ExtractList | null
  confirmations: ConfirmState
  onToggle: (tab: string, itemId: string, checked: boolean) => void
}) {
  if (!extraction) return <Text type="secondary">无规则粗分数据</Text>

  const selectedItems = extraction.items.filter((i) => i.selected)
  const redFlags = extraction.red_flags ?? []
  const redFlagItems = new Set(redFlags.map((rf: Record<string, unknown>) => rf.item as string))

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      {redFlags.length > 0 && (
        <Tag color="warning">{redFlags.length} 条标红提示（不阻断，确认后解除）</Tag>
      )}
      {selectedItems.map((item: ExtractItem) => {
        const hasRed = redFlagItems.has(item.key) || item.status === 'missing'
        return (
          <div key={item.key} style={{ border: '1px solid #f0f0f0', padding: 12, borderRadius: 8 }}>
            <Space style={{ marginBottom: 8 }}>
              <Text strong>{item.label}</Text>
              <Tag>{item.key}</Tag>
              {hasRed && <Tag color="error">标红</Tag>}
              {item.status === 'missing' && <Tag color="warning">未识别</Tag>}
            </Space>
            {item.matches.length === 0 ? (
              <Checkbox
                checked={confirmations[`extraction:${item.key}:0`] ?? false}
                onChange={(e) => onToggle('extraction', `${item.key}:0`, e.target.checked)}
              >
                无匹配项（人工确认此要素已检查）
              </Checkbox>
            ) : (
              item.matches.map((m, i) => {
                const itemId = `${item.key}:${i}`
                const matchRed = m.anchor_verified === false
                return (
                  <div key={itemId} style={{ marginLeft: 16, marginBottom: 4 }}>
                    <Checkbox
                      checked={confirmations[`extraction:${itemId}`] ?? false}
                      onChange={(e) => onToggle('extraction', itemId, e.target.checked)}
                    >
                      <Space>
                        {m.heading && <Text>{m.heading}</Text>}
                        {m.snippet && <Text type="secondary">{m.snippet}</Text>}
                        {matchRed && <Tag color="error">锚点未验证</Tag>}
                        {m.anchor && <Text code>{m.anchor}</Text>}
                      </Space>
                    </Checkbox>
                  </div>
                )
              })
            )}
          </div>
        )
      })}
    </Space>
  )
}

// ---------- Tab 2: 评分表 ----------

function ScoreTab({
  score,
  confirmations,
  onToggle,
}: {
  score: ScoreTable | null
  confirmations: ConfirmState
  onToggle: (tab: string, itemId: string, checked: boolean) => void
}) {
  if (!score) return <Text type="secondary">无评分表数据</Text>

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Space>
        {score.total_score_check.ok === false && (
          <Tag color="error">
            合计 {score.total_score_check.actual} ≠ {score.total_score_check.expected}（标红不阻断）
          </Tag>
        )}
        {score.schema_validated === false && (
          <Tag color="error">Schema 校验未通过（标红不阻断）</Tag>
        )}
        {score.red_flags.length > 0 && (
          <Tag color="warning">{score.red_flags.length} 条标红提示</Tag>
        )}
      </Space>
      {score.categories.map((cat, ci) => (
        <div key={ci} style={{ border: '1px solid #f0f0f0', padding: 12, borderRadius: 8 }}>
          <Text strong>{cat.name}</Text>
          {cat.items.map((si, ii) => {
            const itemId = `${ci}:${ii}`
            return (
              <div key={itemId} style={{ marginLeft: 16, marginBottom: 4 }}>
                <Checkbox
                  checked={confirmations[`score:${itemId}`] ?? false}
                  onChange={(e) => onToggle('score', itemId, e.target.checked)}
                >
                  <Space>
                    <Text>{si.name}</Text>
                    {si.score !== null && <Tag color="blue">{si.score} 分</Tag>}
                    {si.materials.length > 0 && (
                      <Text type="secondary">材料：{si.materials.join('、')}</Text>
                    )}
                  </Space>
                </Checkbox>
              </div>
            )
          })}
        </div>
      ))}
    </Space>
  )
}

// ---------- Tab 3: 投标文件格式 ----------

function DocxTab({
  docx,
  confirmations,
  onToggle,
  enterpriseId,
  projectId,
}: {
  docx: DocxManifest | null
  confirmations: ConfirmState
  onToggle: (tab: string, itemId: string, checked: boolean) => void
  enterpriseId: string
  projectId: string
}) {
  if (!docx) return <Text type="secondary">无投标文件格式数据</Text>

  const handleOpen = async (f: DocxFile) => {
    try {
      await window.bid.shell.openDocxFile(enterpriseId, projectId, f.source_stem, f.file)
    } catch {
      // Main 侧路径校验失败或文件不存在
    }
  }

  const columns = [
    {
      title: '确认',
      key: 'confirmed',
      width: 60,
      render: (_v: unknown, f: DocxFile) => (
        <Checkbox
          checked={confirmations[`docx:${f.checkpoint_key}`] ?? false}
          onChange={(e) => onToggle('docx', f.checkpoint_key, e.target.checked)}
        />
      ),
    },
    {
      title: '文件',
      key: 'file',
      render: (_v: unknown, f: DocxFile) => (
        <Button type="link" onClick={() => handleOpen(f)}>
          {f.seq.toString().padStart(2, '0')}_{f.title}.docx
        </Button>
      ),
    },
    {
      title: '来源',
      key: 'source',
      dataIndex: 'source_stem',
    },
    {
      title: '页码',
      key: 'pages',
      render: (_v: unknown, f: DocxFile) =>
        f.start_page !== null && f.end_page !== null ? `${f.start_page}-${f.end_page}` : '-',
    },
    {
      title: '状态',
      key: 'state',
      render: (_v: unknown, f: DocxFile) => {
        if (f.state === 'success') return <Tag color="success">成功</Tag>
        if (f.state === 'error') return <Tag color="error">失败</Tag>
        return <Tag>{f.state}</Tag>
      },
    },
    {
      title: '红字',
      key: 'red_flags',
      render: (_v: unknown, f: DocxFile) =>
        f.red_flags > 0 ? (
          <Tag color="warning">{f.red_flags} 处</Tag>
        ) : (
          <Text type="secondary">-</Text>
        ),
    },
  ]

  const allFiles = docx.sources.flatMap((s) => s.files)

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      {docx.sources.some((s) => !s.found) && (
        <Tag color="warning">
          未识别到「投标文件格式」章节：
          {docx.sources
            .filter((s) => !s.found)
            .map((s) => s.source_stem)
            .join('、')}
        </Tag>
      )}
      <Table
        dataSource={allFiles}
        columns={columns}
        rowKey="checkpoint_key"
        pagination={false}
        size="small"
      />
    </Space>
  )
}
