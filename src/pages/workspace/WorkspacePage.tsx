import { BankOutlined } from '@ant-design/icons'
import PagePlaceholder from '../../components/PagePlaceholder'

export default function WorkspacePage() {
  return (
    <PagePlaceholder
      icon={<BankOutlined />}
      title="企业/项目管理"
      description="企业—项目两级数据管理（创建、编辑、切换、委托代理人、回收站）将在 Task 5 实现。"
    />
  )
}
