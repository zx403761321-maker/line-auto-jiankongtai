import { createRouter, createWebHistory } from 'vue-router'
import Overview from '../views/Overview.vue'
import Servers from '../views/Servers.vue'
import Devices from '../views/Devices.vue'
import Alerts from '../views/Alerts.vue'
import TaskCenter from '../views/TaskCenter.vue'

const routes = [
  { path: '/', redirect: '/overview' },
  { path: '/overview', name: 'overview', component: Overview },
  { path: '/servers', name: 'servers', component: Servers },
  { path: '/devices', name: 'devices', component: Devices },
  { path: '/alerts', name: 'alerts', component: Alerts },
  { path: '/tasks', name: 'tasks', component: TaskCenter },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
