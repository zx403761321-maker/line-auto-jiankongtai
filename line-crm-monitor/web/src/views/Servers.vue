<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getServers, getDevices } from '../api'
import { deviceAnomalyOf } from '../utils/deviceAnomaly'

const servers = ref([])
const devices = ref([])
const loading = ref(true)

function fmtTime(v) {
  if (!v) return '—'
  return new Date(v).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei', hour12: false })
}
function fmtAgo(s) {
  if (s == null) return '—'
  if (s < 60) return `${Math.round(s)} 秒前`
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`
  return `${Math.floor(s / 3600)} 小时前`
}

// 按 server_id 聚合设备统计（云手机 / 在线 / 异常）
const devicesByServer = computed(() => {
  const map = {}
  for (const d of devices.value) {
    if (!map[d.server_id]) map[d.server_id] = { total: 0, online: 0, abnormal: 0 }
    const s = map[d.server_id]
    s.total += 1
    if (d.online_status === 'online') s.online += 1
    if (deviceAnomalyOf(d)) s.abnormal += 1
  }
  return map
})

function deviceStats(serverId) {
  return devicesByServer.value[serverId] || { total: 0, online: 0, abnormal: 0 }
}

let timer = null
async function load() {
  try {
    const [s, d] = await Promise.all([getServers(), getDevices()])
    servers.value = s
    devices.value = d
  } catch (e) {
    // 401 由拦截器统一触发登录框
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 15000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div v-loading="loading">
    <el-table :data="servers" border stripe>
      <el-table-column prop="server_id" label="server_id" width="120" />
      <el-table-column label="server_ip" width="150">
        <template #default="{ row }">{{ row.server_ip || '—' }}</template>
      </el-table-column>
      <el-table-column label="online" width="100">
        <template #default="{ row }">
          <el-tag :type="row.online ? 'success' : 'danger'" size="small">
            {{ row.online ? 'online' : 'offline' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="云手机" width="90">
        <template #default="{ row }">{{ deviceStats(row.server_id).total }}</template>
      </el-table-column>
      <el-table-column label="在线" width="90">
        <template #default="{ row }">{{ deviceStats(row.server_id).online }}</template>
      </el-table-column>
      <el-table-column label="异常" width="90">
        <template #default="{ row }">
          <span :class="{ abnormal: deviceStats(row.server_id).abnormal > 0 }">
            {{ deviceStats(row.server_id).abnormal }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="CPU %" width="90">
        <template #default="{ row }">{{ row.cpu_percent?.toFixed(1) ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="内存 %" width="90">
        <template #default="{ row }">{{ row.memory_percent?.toFixed(1) ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="磁盘 %" width="90">
        <template #default="{ row }">{{ row.disk_percent?.toFixed(1) ?? '—' }}</template>
      </el-table-column>
      <el-table-column prop="agent_version" label="agent 版本" width="110" />
      <el-table-column label="最后心跳" width="180">
        <template #default="{ row }">{{ fmtTime(row.last_heartbeat_at) }}</template>
      </el-table-column>
      <el-table-column label="心跳新鲜度" width="130">
        <template #default="{ row }">{{ fmtAgo(row.seconds_since_seen) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.abnormal {
  color: #f56c6c;
  font-weight: 600;
}
</style>
