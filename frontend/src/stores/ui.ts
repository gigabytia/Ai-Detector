import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type Theme = 'light' | 'dark'

const THEME_STORAGE_KEY = 'ai-detector.theme'

function readStoredTheme(): Theme {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

/** Client-only UI preferences. Server data lives in Vue Query, never here. */
export const useUiStore = defineStore('ui', () => {
  const theme = ref<Theme>(readStoredTheme())

  watch(
    theme,
    (value) => {
      document.documentElement.classList.toggle('dark', value === 'dark')
      try {
        localStorage.setItem(THEME_STORAGE_KEY, value)
      } catch {
        // Storage may be disabled; keep the selected theme in memory.
      }
    },
    { immediate: true },
  )

  function toggleTheme(): void {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  return { theme, toggleTheme }
})
