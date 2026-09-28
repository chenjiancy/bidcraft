import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type ThemeMode = 'light' | 'dark'

export interface EnterpriseSummary {
  id: string
  name: string
  agent: string
}

export interface ProjectSummary {
  id: string
  name: string
  agent: string
}

interface AppState {
  /** 明/暗主题（持久化） */
  themeMode: ThemeMode
  /**
   * 解析清单是否已确认（PARSE_CONFIRMED 门禁信号）。
   * Task 2 为前端模拟状态；Task 7 起由真实项目状态机驱动。
   */
  isParseConfirmed: boolean
  /** 当前企业（持久化，跨重启记住） */
  currentEnterprise: EnterpriseSummary | null
  /** 当前项目（不持久化，每次启动需重新选） */
  currentProject: ProjectSummary | null
  toggleTheme: () => void
  setThemeMode: (mode: ThemeMode) => void
  setParseConfirmed: (confirmed: boolean) => void
  setCurrentEnterprise: (ent: EnterpriseSummary | null) => void
  setCurrentProject: (proj: ProjectSummary | null) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      themeMode: 'light',
      isParseConfirmed: false,
      currentEnterprise: null,
      currentProject: null,
      toggleTheme: () => set((s) => ({ themeMode: s.themeMode === 'light' ? 'dark' : 'light' })),
      setThemeMode: (themeMode) => set({ themeMode }),
      setParseConfirmed: (isParseConfirmed) => set({ isParseConfirmed }),
      // 切换企业时清空当前项目（项目隔离边界）
      setCurrentEnterprise: (currentEnterprise) => set({ currentEnterprise, currentProject: null }),
      setCurrentProject: (currentProject) => set({ currentProject }),
    }),
    {
      name: 'bidcraft-ui',
      storage: createJSONStorage(() => localStorage),
      // 持久化主题与当前企业；项目与解锁状态每次启动重置
      partialize: (s) => ({
        themeMode: s.themeMode,
        currentEnterprise: s.currentEnterprise,
      }),
    },
  ),
)
