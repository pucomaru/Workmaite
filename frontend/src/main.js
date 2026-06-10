import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap-icons/font/bootstrap-icons.css'
import 'bootstrap/dist/js/bootstrap.bundle.min.js'
import './style.css'
import './styles/archive/agent.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')

// Bootstrap 툴팁 전역 초기화 — [data-bs-toggle="tooltip"] 요소에 적용
import('bootstrap').then(({ Tooltip }) => {
  const init = () => document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
    if (!Tooltip.getInstance(el)) new Tooltip(el)
  })
  init()
  new MutationObserver(init).observe(document.body, { childList: true, subtree: true })
})
