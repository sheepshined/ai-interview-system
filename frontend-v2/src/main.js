import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { reveal } from './composables/useReveal'
import './styles/tokens.css'
import './styles/base.css'
import './styles/components.css'
import './styles/app.css'

const app = createApp(App)
app.directive('reveal', reveal)
app.use(router)
app.mount('#app')