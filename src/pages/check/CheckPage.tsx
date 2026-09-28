import { AuditOutlined } from '@ant-design/icons'
import PagePlaceholder from '../../components/PagePlaceholder'

export default function CheckPage() {
  return (
    <PagePlaceholder
      icon={<AuditOutlined />}
      title="标书检查"
      description="标书检查属第二期内容（FR-6 需求待讨论）；当前仅落地导航与门禁位置。"
    />
  )
}
