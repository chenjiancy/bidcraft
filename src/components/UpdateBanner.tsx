import { useEffect, useState } from 'react'
import { Button, Progress } from 'antd'

export interface UpdateBannerProps {
  /** 是否在桌面端运行（非 Web 环境才显示） */
  enabled?: boolean
}

/**
 * 更新提示横幅。
 *
 * - checking：显示进度条（不遮挡操作）
 * - available：显示"新版本可用，重启安装"按钮
 * - downloaded：显示"已下载，重启安装"按钮
 * - error / not_available：自动消失（5s）
 */
export default function UpdateBanner({ enabled = true }: UpdateBannerProps) {
  const [status, setStatus] = useState<string>('idle')
  const [percent, setPercent] = useState<number>(0)
  const [message, setMessage] = useState<string>('')
  const [show, setShow] = useState<boolean>(false)

  useEffect(() => {
    if (!enabled || typeof window.bid?.update === 'undefined') return

    const cleanupStatus = window.bid.update.onStatus((payload: unknown) => {
      const p = payload as { status: string; message?: string }
      setStatus(p.status)
      setMessage(p.message ?? '')
      setShow(true)

      if (p.status === 'not_available' || p.status === 'error') {
        setTimeout(() => setShow(false), 5000)
      }
    })

    const cleanupProgress = window.bid.update.onDownloadProgress((payload: unknown) => {
      const p = payload as { percent: number }
      setPercent(p.percent)
    })

    return () => {
      cleanupStatus()
      cleanupProgress()
    }
  }, [enabled])

  const handleRestart = () => {
    // electron-updater autoInstallOnAppQuit: true → quit 后自动安装
    window.location.reload()
  }

  if (!show) return null

  return (
    <div
      className="bc-update-banner"
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 100,
        background: status === 'available' || status === 'downloaded' ? '#0d9488' : '#f0f9ff',
        color: status === 'available' || status === 'downloaded' ? '#fff' : '#0c4a6e',
        padding: '6px 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        fontSize: 13,
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        borderBottom: '1px solid rgba(0,0,0,0.06)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
        {(status === 'checking' || status === 'downloading') && (
          <Progress
            type="circle"
            size={18}
            percent={percent}
            showText={false}
            strokeColor={status === 'available' || status === 'downloaded' ? '#fff' : '#0d9488'}
            trailColor="rgba(255,255,255,0.3)"
          />
        )}
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {status === 'checking' && '检查更新中…'}
          {status === 'downloading' && `正在下载更新 ${percent}%`}
          {status === 'available' && '发现新版本，重启即可安装'}
          {status === 'downloaded' && '更新已下载完成，重启即可安装'}
          {status === 'not_available' && '当前已是最新版本'}
          {status === 'error' && `更新检查失败：${message}`}
        </span>
      </div>

      {(status === 'available' || status === 'downloaded') && (
        <Button
          type="primary"
          size="small"
          onClick={handleRestart}
          style={{
            flexShrink: 0,
            background: '#fff',
            color: '#0d9488',
            border: 'none',
            fontWeight: 600,
          }}
        >
          重启安装
        </Button>
      )}

      {status === 'error' && (
        <Button
          size="small"
          type="text"
          onClick={() => setShow(false)}
          style={{ color: 'inherit', flexShrink: 0 }}
        >
          忽略
        </Button>
      )}
    </div>
  )
}
