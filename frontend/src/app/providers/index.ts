import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import type { App } from 'vue'

import { router } from '@/app/router'
import { i18n } from '@/i18n'

export function installProviders(app: App): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { staleTime: 2_000, refetchOnWindowFocus: false } },
  })
  app.use(createPinia())
  app.use(router)
  app.use(i18n)
  app.use(VueQueryPlugin, { queryClient })
}
