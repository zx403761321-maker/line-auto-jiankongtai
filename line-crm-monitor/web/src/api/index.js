import axios from 'axios'

const http = axios.create({ baseURL: '/', timeout: 10000 })

let unauthorizedHandler = null
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn
}

// 401 统一处理：触发登录框
http.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err.response && err.response.status === 401 && unauthorizedHandler) {
      unauthorizedHandler()
    }
    return Promise.reject(err)
  }
)

export async function getServers() {
  const { data } = await http.get('/api/servers')
  return data.servers || []
}

export async function getDevices() {
  const { data } = await http.get('/api/devices')
  return data.devices || []
}

export async function getAnomalyHistory(days = 30) {
  const { data } = await http.get('/api/devices/anomaly-history', { params: { days } })
  return data.history || []
}

export async function login(username, password) {
  await http.post('/api/auth/login', { username, password })
}

export async function logout() {
  await http.post('/api/auth/logout')
}

export async function getDaily(date) {
  const { data } = await http.get('/api/daily', { params: { date } })
  return data
}

export async function getAddTrend(window, month) {
  const { data } = await http.get('/api/stats/trend', { params: { window, month } })
  return data
}
