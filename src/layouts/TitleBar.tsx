import { useAppStore } from '../stores/useAppStore'

/**
 * 自定义标题栏（替代被隐藏的系统标题栏）。
 *
 * - 整条为窗口拖拽区（-webkit-app-region: drag），右侧留白给 Electron 原生窗口控件
 *   （由 titleBarOverlay 绘制，悬停最大化按钮仍有 Windows Snap Layouts 预览）。
 * - 展示当前企业/项目作用域，避免用户误在别的项目里操作。
 */
export default function TitleBar() {
  const currentEnterprise = useAppStore((s) => s.currentEnterprise)
  const currentProject = useAppStore((s) => s.currentProject)

  return (
    <header className="bc-titlebar">
      <span className="bc-brand-mark" aria-hidden="true">
        标
      </span>
      <span className="bc-brand-name">AI标书制作</span>
      <div className="bc-titlebar-ctx">
        {currentEnterprise ? (
          <>
            <span className="bc-ctx-item">{currentEnterprise.name}</span>
            {currentProject && (
              <>
                <span className="bc-ctx-sep" aria-hidden="true">
                  ›
                </span>
                <span className="bc-ctx-item">{currentProject.name}</span>
              </>
            )}
          </>
        ) : (
          <span className="bc-ctx-item bc-ctx-item--muted">未选择企业</span>
        )}
      </div>
    </header>
  )
}
