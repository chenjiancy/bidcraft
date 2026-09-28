import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type ThemeMode = 'light' | 'dark'

interface AppState {
  /** 明/暗主题（持久化） */
  themeMode: ThemeMode
  /**
   * 解析清单是否已确认（PARSE_CONFIRMED 门禁信号）。
   * Task 2 为前端模拟状态；Task 7 起由真实项目状态机驱动。
   */
  isParseConfirmed: boolean
  toggleTheme: () => void
  setThemeMode: (mode: ThemeMode) => void
  setParseConfirmed: (confirmed: boolean) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      themeMode: 'light',
      isParseConfirmed: false,
      toggleTheme: () => set((s) => ({ themeMode: s.themeMode === 'light' ? 'dark' : 'light' })),
      setThemeMode: (themeMode) => set({ themeMode }),
      setParseConfirmed: (isParseConfirmed) => set({ isParseConfirmed }),
    }),
    {
      name: 'bidcraft-ui',
      storage: createJSONStorage(() => localStorage),
      // 仅持久化主题；解锁状态每次启动重置（安全默认）
      partialize: (s) => ({ themeMode: s.themeMode }),
    },
  ),
)
