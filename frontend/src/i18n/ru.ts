export const ru = {
  app: { title: 'AI Detector' },
  nav: {
    monitoring: 'Мониторинг',
    events: 'События',
    analytics: 'Аналитика',
    cameras: 'Камеры',
    settings: 'Настройки',
  },
  theme: { toggle: 'Переключить тему', light: 'Светлая тема', dark: 'Тёмная тема' },
  system: {
    title: 'Состояние системы',
    summary: {
      ok: 'Система работает',
      degraded: 'Работа ограничена',
      down: 'Нет связи с сервером',
      loading: 'Проверка…',
    },
    dependency: { database: 'База данных', redis: 'Шина событий (Redis)' },
    ok: 'Доступно',
    unavailable: 'Недоступно',
    workers: 'Обработчики видео',
    noWorkers: 'Обработчик видео не запущен. Камеры не будут обрабатываться.',
    uptime: 'Работает {minutes} мин',
    checkedAt: 'Проверено в {time}',
    loadError: 'Не удалось получить состояние системы. Повторная попытка…',
  },
  placeholder: 'Раздел появится на следующих этапах разработки.',
} as const

export type MessageSchema = typeof ru
