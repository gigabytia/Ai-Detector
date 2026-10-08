import 'vue-sonner/style.css'
import '@/styles/main.css'

import { createApp } from 'vue'

import App from '@/app/App.vue'
import { installProviders } from '@/app/providers'

const app = createApp(App)
installProviders(app)
app.mount('#app')
