<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getDevices } from '../api'

const devices = ref([])
const loading = ref(true)
const onlyAbnormal = ref(false)
const serverFilter = ref('')

const serverIds = computed(() => [...new Set(devices.value.map((d) => d.server_id))].sort())

const filtered = computed(() => {
  let list = devices.value
  if (serverFilter.value) list = list.filter((d) => d.server_id === serverFilter.value)
  if (onlyAbnormal.value) {
    list = list.filter((d) => d.needs_replacement === true || d.online_status === 'offline')
  }
  return list
})

function fmtTime(v) {
  if (!v) return '—'
  return new Date(v).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei', hour12: false })
}
function fmtCooldown(v) {
  if (!v) return '—'
  const ms = new Date(v).getTime() - Date.now()
  if (ms <= 0) return '已结束'
  const m = Math.floor(ms / 60000)
  const d = Math.floor(m / 1440)
  const h = Math.floor((m % 1440) / 60)
  const mm = m % 60
  if (d > 0) return `${d}天 ${h}时`
  if (h > 0) return `${h}时 ${mm}分`
  return `${mm}分`
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

// 展示层中文化：API 保持英文枚举，这里只做文案映射（颜色逻辑不动）
const RISK_STATUS_LABEL = { normal: '正常', warning: '警告', critical: '严重' }
const ACCOUNT_STATUS_LABEL = { active: '正常', cooling_down: '冷却中', needs_replacement: '需换号' }

let timer = null
async function load() {
  try {
    devices.value = await getDevices()
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
    <div class="toolbar">
      <el-select v-model="serverFilter" placeholder="全部服务器" clearable style="width: 180px">
        <el-option v-for="s in serverIds" :key="s" :label="s" :value="s" />
      </el-select>
      <el-switch v-model="onlyAbnormal" active-text="只看异常" />
      <span class="count">共 {{ filtered.length }} 台</span>
    </div>
    <el-table :data="filtered" border stripe>
      <el-table-column prop="device_id" label="device_id" sortable width="140" />
      <el-table-column prop="server_id" label="server_id" width="110" />
      <el-table-column label="online_status" width="120">
        <template #default="{ row }">
          <el-tag :type="row.online_status === 'online' ? 'success' : 'danger'" size="small">
            {{ row.online_status || '—' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="today_success" label="今日成功" sortable width="100" />
      <el-table-column prop="today_fail" label="今日失败" sortable width="100" />
      <el-table-column prop="risk_score" label="风险分数" sortable width="110" />
      <el-table-column label="风险状态" width="110">
        <template #default="{ row }">
          <el-tag :type="riskTagType(row.risk_status)" size="small" :title="row.risk_reason || ''">
            {{ RISK_STATUS_LABEL[row.risk_status] || row.risk_status || '—' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="账号状态" width="150">
        <template #default="{ row }">
          <el-tag :type="accountTagType(row.account_status)" size="small" :title="row.account_reason || ''">
            {{ ACCOUNT_STATUS_LABEL[row.account_status] || row.account_status || '—' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="需换号" width="140">
        <template #default="{ row }">
          <el-tag v-if="row.needs_replacement" type="danger" size="small">需换号</el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="冷却倒计时" width="130">
        <template #default="{ row }">{{ fmtCooldown(row.cooldown_until) }}</template>
      </el-table-column>
      <el-table-column label="最后更新" min-width="180">
        <template #default="{ row }">{{ fmtTime(row.status_updated_at) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
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
</style>
