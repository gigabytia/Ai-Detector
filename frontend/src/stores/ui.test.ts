import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'

import { useUiStore } from './ui'

describe('ui store', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.className = ''
    setActivePinia(createPinia())
  })

  it('defaults to the light theme', () => {
    expect(useUiStore().theme).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('toggles and persists the dark theme', async () => {
    const store = useUiStore()
    store.toggleTheme()
    await nextTick()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(localStorage.getItem('ai-detector.theme')).toBe('dark')
  })
})
