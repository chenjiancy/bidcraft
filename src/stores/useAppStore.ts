import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type ThemeMode = 'light' | 'dark'

/**
 * 视为「解析清单已确认」的解析状态集合（PARSE_CONFIRMED 及其之后的全部状态）。
 * 用于商务标模块门禁：PARSE_CONFIRMED 起即可进入 /bid 完成格式清单复核。
 */
const PARSE_CONFIRMED_STATUSES = [
  'PARSE_CONFIRMED',
  'FORMAT_REVIEW',
  'FORMAT_CONFIRMED',
  'MATERIAL_LOOP',
  'MATERIAL_CONFIRMED',
  'TEMPLATE_MATCHED',
  'TEMPLATE_REVIEW',
  'READY_TO_RENDER',
]

/**
 * 视为「业务模块已解锁」的解析状态集合（格式清单已确认）。
 * Task 14：FORMAT_CONFIRMED 解锁；Task 16：进入/完成素材提取循环后仍保持解锁；
 * Task 18：进入模板匹配（TEMPLATE_MATCHED 起）后仍保持解锁。
 */
const UNLOCKED_FORMAT_STATUSES = [
  'FORMAT_CONFIRMED',
  'MATERIAL_LOOP',
  'MATERIAL_CONFIRMED',
  'TEMPLATE_MATCHED',
  'TEMPLATE_REVIEW',
  'READY_TO_RENDER',
]

/** 视为「素材提取清单已确认」的状态集合（MATERIAL_CONFIRMED 及其后续模板匹配状态）。 */
const MATERIAL_CONFIRMED_STATUSES = [
  'MATERIAL_CONFIRMED',
  'TEMPLATE_MATCHED',
  'TEMPLATE_REVIEW',
  'READY_TO_RENDER',
]

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
   * Task 13 起由后端 parse_status === 'PARSE_CONFIRMED' 派生。
   * setParseConfirmed 保留供 walking-skeleton 测试 mock。
   */
  isParseConfirmed: boolean
  /** 后端解析状态（Task 13：派生 isParseConfirmed） */
  parseStatus: string | undefined
  /**
   * 商务标格式清单确认状态（FORMAT_CONFIRMED 门禁信号）。
   * Task 14：由后端 parse_status === 'FORMAT_CONFIRMED' 派生。
   */
  formatStatus: string | undefined
  isFormatListConfirmed: boolean
  /**
   * 素材提取清单是否已确认保存（MATERIAL_CONFIRMED 门禁信号）。
   * Task 16：由后端 parse_status === 'MATERIAL_CONFIRMED' 派生。
   */
  materialStatus: string | undefined
  isMaterialConfirmed: boolean
  /** 当前企业（持久化，跨重启记住） */
  currentEnterprise: EnterpriseSummary | null
  /** 当前项目（不持久化，每次启动需重新选） */
  currentProject: ProjectSummary | null
  toggleTheme: () => void
  setThemeMode: (mode: ThemeMode) => void
  setParseConfirmed: (confirmed: boolean) => void
  setParseStatus: (status: string | undefined) => void
  setFormatStatus: (status: string | undefined) => void
  setMaterialStatus: (status: string | undefined) => void
  setCurrentEnterprise: (ent: EnterpriseSummary | null) => void
  setCurrentProject: (proj: ProjectSummary | null) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      themeMode: 'light',
      isParseConfirmed: false,
      parseStatus: undefined,
      formatStatus: undefined,
      isFormatListConfirmed: false,
      materialStatus: undefined,
      isMaterialConfirmed: false,
      currentEnterprise: null,
      currentProject: null,
      toggleTheme: () => set((s) => ({ themeMode: s.themeMode === 'light' ? 'dark' : 'light' })),
      setThemeMode: (themeMode) => set({ themeMode }),
      setParseConfirmed: (isParseConfirmed) => set({ isParseConfirmed }),
      setParseStatus: (parseStatus) =>
        set({
          parseStatus,
          isParseConfirmed: PARSE_CONFIRMED_STATUSES.includes(parseStatus ?? ''),
        }),
      setFormatStatus: (formatStatus) =>
        set({
          formatStatus,
          isFormatListConfirmed: UNLOCKED_FORMAT_STATUSES.includes(formatStatus ?? ''),
          isMaterialConfirmed: MATERIAL_CONFIRMED_STATUSES.includes(formatStatus ?? ''),
        }),
      setMaterialStatus: (materialStatus) =>
        set({
          materialStatus,
          isMaterialConfirmed: MATERIAL_CONFIRMED_STATUSES.includes(materialStatus ?? ''),
        }),
      // 切换企业时清空当前项目并重置解析确认（项目隔离边界 + 门禁安全）
      setCurrentEnterprise: (currentEnterprise) =>
        set({
          currentEnterprise,
          currentProject: null,
          isParseConfirmed: false,
          parseStatus: undefined,
          isFormatListConfirmed: false,
          formatStatus: undefined,
          materialStatus: undefined,
          isMaterialConfirmed: false,
        }),
      // 切换项目时重置解析确认（不同项目的解析状态独立）
      setCurrentProject: (currentProject) =>
        set({
          currentProject,
          isParseConfirmed: false,
          parseStatus: undefined,
          isFormatListConfirmed: false,
          formatStatus: undefined,
          materialStatus: undefined,
          isMaterialConfirmed: false,
        }),
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
