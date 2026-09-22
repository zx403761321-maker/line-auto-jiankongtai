<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getServers, getDevices } from '../api'
import { deviceAnomalyOf } from '../utils/deviceAnomaly'

const servers = ref([])
const devices = ref([])
const loading = ref(true)

const serverFilter = ref('')
const onlyAbnormal = ref(false)
const keyword = ref('')

// 设备异常 dimension → 中文（与 Alerts.vue 异常中心标签保持一致）
const ANOMALY_LABEL = {
  account_needs_replacement: '需换号',
  risk_critical: '风险临界',
  device_offline: '设备离线',
}

// 今日运行判断：last_task_at 是否落在当天 Asia/Taipei。
// 不用 today_success/today_fail 判断——业务侧 daily_* 惰性重置，
// 停运设备会残留「最后一次运行日」的旧值，会误判为今天在跑。
function isToday(v) {
  if (!v) return false
  const opts = { timeZone: 'Asia/Taipei' }
  return (
    new Date(v).toLocaleDateString('zh-TW', opts) ===
    new Date().toLocaleDateString('zh-TW', opts)
  )
}

function fmtTime(v) {
  if (!v) return '—'
  return new Date(v).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei', hour12: false })
}

function successRate(d) {
  const ok = d.today_success || 0
  const fail = d.today_fail || 0
  const total = ok + fail
  if (total === 0) return '—'
  return ((ok / total) * 100).toFixed(1) + '%'
}

function riskTagType(s) {
  if (s === 'critical') return 'danger'
  if (s === 'warning') return 'warning'
  return 'info'
}
function accountTagType(s) {
  if (s === 'needs_replacement') return 'danger'
  if (s === 'cooling_down') return 'warning'
  return 'success'
}

function rowClassName({ row }) {
  return deviceAnomalyOf(row) ? 'abnormal-row' : ''
}

// 服务器维度汇总（前端聚合，不做复杂图表/排行）
const devicesByServer = computed(() => {
  const map = {}
  for (const d of devices.value) {
    if (!map[d.server_id]) {
      map[d.server_id] = { total: 0, activeToday: 0, abnormal: 0, success: 0, fail: 0 }
    }
    const s = map[d.server_id]
    s.total += 1
    if (isToday(d.last_task_at)) s.activeToday += 1
    if (deviceAnomalyOf(d)) s.abnormal += 1
    s.success += d.today_success || 0
    s.fail += d.today_fail || 0
  }
  return map
})

const serverSummary = computed(() =>
  servers.value.map((s) => ({
    server_id: s.server_id,
    ...(devicesByServer.value[s.server_id] || {
      total: 0,
      activeToday: 0,
      abnormal: 0,
      success: 0,
      fail: 0,
    }),
  }))
)

const filtered = computed(() => {
  let list = devices.value
  if (serverFilter.value) list = list.filter((d) => d.server_id === serverFilter.value)
  if (onlyAbnormal.value) list = list.filter((d) => deviceAnomalyOf(d))
  const kw = keyword.value.trim().toLowerCase()
  if (kw) list = list.filter((d) => (d.device_id || '').toLowerCase().includes(kw))
  return list
})

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
    <!-- 服务器维度汇总 -->
    <el-table :data="serverSummary" border size="small" class="summary-table">
      <el-table-column prop="server_id" label="服务器" width="120" />
      <el-table-column label="设备数量" width="100">
        <template #default="{ row }">{{ row.total }}</template>
      </el-table-column>
      <el-table-column label="今日运行" width="100">
        <template #default="{ row }">{{ row.activeToday }}</template>
      </el-table-column>
      <el-table-column label="异常设备" width="100">
        <template #default="{ row }">
          <span :class="{ abnormal: row.abnormal > 0 }">{{ row.abnormal }}</span>
        </template>
      </el-table-column>
      <el-table-column label="成功" width="100">
        <template #default="{ row }">{{ row.success }}</template>
      </el-table-column>
      <el-table-column label="失败" width="100">
        <template #default="{ row }">
          <span :class="{ fail: row.fail > 0 }">{{ row.fail }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 工具栏 -->
    <div class="toolbar">
      <el-select v-model="serverFilter" placeholder="全部服务器" clearable style="width: 180px">
        <el-option v-for="s in servers" :key="s.server_id" :label="s.server_id" :value="s.server_id" />
      </el-select>
      <el-switch v-model="onlyAbnormal" active-text="仅看异常" />
      <el-input v-model="keyword" placeholder="搜索 device_id" clearable style="width: 220px" />
      <span class="count">共 {{ filtered.length }} 台</span>
    </div>

    <!-- 设备运行统计明细 -->
    <el-table :data="filtered" border stripe :row-class-name="rowClassName">
      <el-table-column prop="server_id" label="server_id" width="110" />
      <el-table-column prop="device_id" label="设备" width="120" />
      <el-table-column label="运行状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.online_status === 'online' ? 'success' : 'danger'" size="small">
            {{ row.online_status || '—' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="今日运行" width="110">
        <template #default="{ row }">
          <el-tag :type="isToday(row.last_task_at) ? 'success' : 'info'" size="small">
            {{ isToday(row.last_task_at) ? '运行' : '今日未运行' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="today_success" label="成功" width="80" />
      <el-table-column label="失败" width="80">
        <template #default="{ row }">
          <span :class="{ fail: (row.today_fail || 0) > 0 }">{{ row.today_fail || 0 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="成功率" width="90">
        <template #default="{ row }">{{ successRate(row) }}</template>
      </el-table-column>
      <el-table-column label="最近任务" width="170">
        <template #default="{ row }">{{ fmtTime(row.last_task_at) }}</template>
      </el-table-column>
      <el-table-column label="风险状态" width="100">
        <template #default="{ row }">
          <el-tag :type="riskTagType(row.risk_status)" size="small">{{ row.risk_status || '—' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="账号状态" width="130">
        <template #default="{ row }">
          <el-tag :type="accountTagType(row.account_status)" size="small">{{ row.account_status || '—' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="异常" width="100">
        <template #default="{ row }">
          <el-tag v-if="deviceAnomalyOf(row)" type="danger" size="small">
            {{ ANOMALY_LABEL[deviceAnomalyOf(row)] }}
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.summary-table {
  margin-bottom: 16px;
}
.toolbar {
  margin-bottom: 12px;
  display: flex;
  gap: 12px;
  align-items: center;
}
.count {
  color: #909399;
  font-size: 13px;
}
.abnormal {
  color: #f56c6c;
  font-weight: 600;
}
.fail {
  color: #e6a23c;
  font-weight: 600;
}
:deep(.abnormal-row) {
  background-color: #fef0f0;
}
</style>
