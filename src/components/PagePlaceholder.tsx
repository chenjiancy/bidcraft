import { Card, Result } from 'antd'
import type { ReactNode } from 'react'

interface PagePlaceholderProps {
  icon: ReactNode
  title: string
  description: ReactNode
  extra?: ReactNode
}

/** 各模块占位页的统一容器（Task 2）。 */
export default function PagePlaceholder({ icon, title, description, extra }: PagePlaceholderProps) {
  return (
    <Card>
      <Result icon={icon} title={title} subTitle={description} extra={extra} />
    </Card>
  )
}
