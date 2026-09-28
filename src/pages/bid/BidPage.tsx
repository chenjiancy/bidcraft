import { FileTextOutlined } from '@ant-design/icons'
import PagePlaceholder from '../../components/PagePlaceholder'

export default function BidPage() {
  return (
    <PagePlaceholder
      icon={<FileTextOutlined />}
      title="商务标制作"
      description="素材提取、模板匹配与比对、docxtpl 逐章渲染将在阶段 1.2（Task 15+）实现。"
    />
  )
}
