import { LockOutlined } from '@ant-design/icons'
import { Result } from 'antd'

/** 未解锁模块的路由兜底视图（FR-2 门禁）。 */
export default function LockedPage({ reason }: { reason?: string }) {
  return (
    <Result
      status="403"
      icon={<LockOutlined />}
      title="模块未解锁"
      subTitle={
        reason ||
        '请先完成招标文件解析，并人工确认保存解析清单（PARSE_CONFIRMED）后，该模块才会解锁。'
      }
    />
  )
}
