<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getServers, getDevices, getDaily, getAddTrend } from '../api'
import { deviceAnomalyOf } from '../utils/deviceAnomaly'
import TaskStatsCard from '../components/TaskStatsCard.vue'
import AddTrendCard from '../components/AddTrendCard.vue'

const servers = ref([])
const devices = ref([])
const loading = ref(true)

// 设备异常 dimension → 中文文案（与 utils/deviceAnomaly 返回值对应）
const DEVICE_REASON = {
  account_needs_replacement: '需换号',
  risk_critical: '风险分数临界',
  device_offline: '设备离线',
}

// ── 今日任务聚合（Stage7-D 后 today_success/today_fail 为「今日」累计）──
const todaySuccess = computed(() => devices.value.reduce((s, d) => s + (d.today_success || 0), 0))
const todayFail = computed(() => devices.value.reduce((s, d) => s + (d.today_fail || 0), 0))
const todayTotal = computed(() => todaySuccess.value + todayFail.value)
const failDeviceCount = computed(() => devices.value.filter((d) => (d.today_fail || 0) > 0).length)

// 第一层：核心指标卡（6）
const metricCards = computed(() => {
  const online = devices.value.filter((d) => d.online_status === 'online').length
  const anomaly = devices.value.filter((d) => deviceAnomalyOf(d)).length
  const rate = todayTotal.value > 0 ? `${Math.round((todaySuccess.value / todayTotal.value) * 100)}%` : '—'
  return [
    { label: '服务器数量', value: servers.value.length },
    { label: '云手机数量', value: devices.value.length },
    { label: '在线设备', value: online },
    { label: '异常设备', value: anomaly },
    { label: '今日任务', value: todayTotal.value },
    { label: '成功率', value: rate },
  ]
})

// 第二层：昨日任务（后端 /api/daily 聚合；跨过第一个台北午夜前为 0）
const yesterday = ref({ success: 0, fail: 0, failed_devices: 0 })

// 添加趋势（周/月累计，后端 /api/stats/trend 聚合；自然周/自然月）
const weekTrend = ref({ window: 'week', points: [], total_success: 0, total_fail: 0 })
const monthTrend = ref({ window: 'month', points: [], total_success: 0, total_fail: 0 })
// 历史月查询结果（仅总数字；折线图保持本月不动）
const monthQueryResult = ref(null)

// 第四层：账号生命周期（3 态，读侧派生）
const accountCards = computed(() => [
  { label: '正常', value: devices.value.filter((d) => d.account_status === 'active').length, color: '#67c23a' },
  { label: '冷却', value: devices.value.filter((d) => d.account_status === 'cooling_down').length, color: '#e6a23c' },
  { label: '需要换号', value: devices.value.filter((d) => d.account_status === 'needs_replacement').length, color: '#f56c6c' },
])

// 第五层：异常提醒（复用 deviceAnomalyOf 单一真源；服务器离线 + 设备异常）
const alerts = computed(() => {
  const list = []
  for (const s of servers.value) {
    if (s.online === false) {
      list.push({ key: `server:${s.server_id}`, text: `${s.server_id}：服务器离线（心跳超时）` })
    }
  }
  for (const d of devices.value) {
    const dimension = deviceAnomalyOf(d)
    if (!dimension) continue
    list.push({
      key: `device:${d.server_id}:${d.device_id}`,
      text: `${d.server_id} / ${d.device_id}：${DEVICE_REASON[dimension]}`,
    })
  }
  list.sort((x, y) => x.text.localeCompare(y.text))
  return list
})

let timer = null
async function load() {
  try {
    const [s, d, y, w, m] = await Promise.all([
      getServers(), getDevices(), getDaily(), getAddTrend('week'), getAddTrend('month'),
    ])
    servers.value = s
    devices.value = d
    yesterday.value = y
    weekTrend.value = w
    monthTrend.value = m
  } catch (e) {
    // 401 由拦截器统一触发登录框
  } finally {
    loading.value = false
  }
}

// 查询指定历史月的累计添加总数（不改变折线图）
async function onMonthQuery(month) {
  try {
    const r = await getAddTrend('month', month)
    monthQueryResult.value = { month, total_success: r.total_success, total_fail: r.total_fail }
  } catch (e) {
    // 401 由拦截器统一触发登录框
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
    <!-- 第一层：核心指标卡 -->
    <div class="section-title">核心指标</div>
    <el-row :gutter="16">
      <el-col v-for="card in metricCards" :key="card.label" :span="4">
        <el-card shadow="hover">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 第二层：今日 / 昨日任务图形化 -->
    <div class="section-title">任务概览</div>
    <el-row :gutter="16">
      <el-col :span="12">
        <TaskStatsCard title="今日任务" :success="todaySuccess" :fail="todayFail" :failed-devices="failDeviceCount" />
      </el-col>
      <el-col :span="12">
        <TaskStatsCard title="昨日任务" :success="yesterday.success" :fail="yesterday.fail" :failed-devices="yesterday.failed_devices" />
      </el-col>
    </el-row>

    <!-- 添加趋势：周/月累计（自然周/自然月） -->
    <div class="section-title">添加趋势</div>
    <el-row :gutter="16">
      <el-col :span="12">
        <AddTrendCard title="周累计添加" :trend="weekTrend" />
      </el-col>
      <el-col :span="12">
        <AddTrendCard
          title="月累计添加"
          :trend="monthTrend"
          queryable
          :query-result="monthQueryResult"
          @query="onMonthQuery"
        />
      </el-col>
    </el-row>

    <!-- 第三层：服务器健康状态 -->
    <div class="section-title">服务器健康状态</div>
    <el-card shadow="hover">
      <div class="server-health">
        <div v-for="s in servers" :key="s.server_id" class="server-item">
          <span class="dot" :class="s.online ? 'ok' : 'bad'"></span>
          <span class="server-name">{{ s.server_id }}</span>
          <span class="server-ip">{{ s.server_ip || '' }}</span>
        </div>
        <div v-if="servers.length === 0" class="empty">暂无服务器</div>
      </div>
    </el-card>

    <!-- 第四层：账号生命周期 -->
    <div class="section-title">账号生命周期</div>
    <el-row :gutter="16">
      <el-col v-for="c in accountCards" :key="c.label" :span="8">
        <el-card shadow="hover">
          <div class="stat-label">{{ c.label }}</div>
          <div class="stat-value" :style="{ color: c.color }">{{ c.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 第五层：异常提醒 -->
    <div class="section-title">异常提醒</div>
    <el-card shadow="hover">
      <div v-if="alerts.length === 0" class="empty ok-text">✅ 无异常</div>
      <div v-else class="alert-list">
        <div v-for="a in alerts" :key="a.key" class="alert-item" @click="$router.push('/alerts')">
          <span class="alert-icon">🔴</span>
          <span class="alert-text">{{ a.text }}</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #606266;
  margin: 20px 0 10px;
}
.stat-label {
  color: #909399;
  font-size: 13px;
}
.stat-value {
  font-size: 28px;
  font-weight: 600;
  margin-top: 8px;
}

/* 第三层：服务器健康状态 */
.server-health {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.server-item {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot.ok {
  background: #67c23a;
}
.dot.bad {
  background: #f56c6c;
}
.server-name {
  font-weight: 600;
  color: #303133;
}
.server-ip {
  color: #909399;
  font-size: 13px;
}

/* 第五层：异常提醒 */
.alert-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.alert-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  background: #fef0f0;
  cursor: pointer;
}
.alert-item:hover {
  background: #fde2e2;
}
.alert-icon {
  flex-shrink: 0;
}
.alert-text {
  color: #f56c6c;
  font-size: 14px;
}
.empty {
  color: #909399;
  font-size: 14px;
  padding: 8px 0;
}
.empty.ok-text {
  color: #67c23a;
}
</style>
