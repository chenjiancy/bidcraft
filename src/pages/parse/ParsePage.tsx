import { FileSearchOutlined } from '@ant-design/icons'
import PagePlaceholder from '../../components/PagePlaceholder'

export default function ParsePage() {
  return (
    <PagePlaceholder
      icon={<FileSearchOutlined />}
      title="招标文件解析"
      description="PDF / Word / 扫描件上传、MinerU 解析、清单人工确认将在阶段 1.1（Task 8+）实现。"
    />
  )
}
