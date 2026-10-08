import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type Theme = 'light' | 'dark'

const THEME_STORAGE_KEY = 'ai-detector.theme'

function readStoredTheme(): Theme {
  return localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light'
}

/** Client-only UI preferences. Server data lives in Vue Query, never here. */
export const useUiStore = defineStore('ui', () => {
  const theme = ref<Theme>(readStoredTheme())

  watch(
    theme,
    (value) => {
      document.documentElement.classList.toggle('dark', value === 'dark')
      localStorage.setItem(THEME_STORAGE_KEY, value)
    },
    { immediate: true },
  )

  function toggleTheme(): void {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  return { theme, toggleTheme }
})
