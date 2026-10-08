import { createI18n } from 'vue-i18n'

import { ru, type MessageSchema } from './ru'

export const i18n = createI18n<[MessageSchema], 'ru'>({
  legacy: false,
  locale: 'ru',
  fallbackLocale: 'ru',
  messages: { ru },
})
