<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  title: { type: String, required: true },
  trend: { type: Object, default: () => ({ window: 'week', points: [], total_success: 0 }) },
  queryable: { type: Boolean, default: false },
  queryResult: { type: Object, default: null },
})

const emit = defineEmits(['query'])
const queryMonth = ref('')

// 历史月查询：只允许已结束的完整月（< 本月 1 号）
function disableFutureOrCurrent(d) {
  const now = new Date()
  return d.getTime() >= new Date(now.getFullYear(), now.getMonth(), 1).getTime()
}

const chartEl = ref(null)
let chart = null

const total = computed(() => props.trend?.total_success ?? 0)
const isWeek = computed(() => props.trend?.window === 'week')

const WEEK_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

// 台北今天 YYYY-MM-DD（UTC+8 无 DST，手动偏移）
function taipeiTodayStr() {
  const t = new Date(Date.now() + 8 * 3600 * 1000)
  const y = t.getUTCFullYear()
  const m = String(t.getUTCMonth() + 1).padStart(2, '0')
  const d = String(t.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function buildOption() {
  const points = props.trend?.points || []
  const success = points.map((p) => p.success)
  const todayIndex = points.findIndex((p) => p.date === taipeiTodayStr())
  const xLabels = isWeek.value
    ? points.map((_, i) => WEEK_LABELS[i] || '')
    : points.map((p) => String(Number(p.date.slice(8))))

  const base = {
    grid: { top: 24, left: 44, right: 16, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0] : params
        if (!p) return ''
        const pt = points[p.dataIndex]
        return pt ? `${pt.date}<br/>添加：${p.value}` : ''
      },
    },
    xAxis: {
      type: 'category',
      data: xLabels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e4e7ed' } },
      axisLabel: { color: '#909399', fontSize: 11, interval: isWeek.value ? 0 : 'auto' },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: '#909399', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f0f2f5' } },
    },
  }

  if (isWeek.value) {
    return {
      ...base,
      series: [
        {
          type: 'bar',
          data: success,
          barWidth: '52%',
          itemStyle: {
            color: (p) => (p.dataIndex === todayIndex ? '#67c23a' : '#c6e2a8'),
            borderRadius: [3, 3, 0, 0],
          },
          label: { show: true, position: 'top', fontSize: 11, color: '#909399' },
        },
      ],
    }
  }
  return {
    ...base,
    series: [
      {
        type: 'line',
        data: success,
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: { color: '#67c23a', width: 2 },
        itemStyle: { color: '#67c23a' },
        areaStyle: { color: 'rgba(103, 194, 58, 0.12)' },
      },
    ],
  }
}

function render() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  chart.setOption(buildOption(), true)
}

function onResize() {
  if (chart) chart.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})

watch(() => props.trend, render, { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<template>
  <el-card shadow="hover">
    <div class="trend-head">
      <div class="trend-head-left">
        <span class="trend-title">{{ title }}</span>
        <span v-if="queryResult" class="trend-query-result">
          {{ queryResult.month }} 累计添加：{{ queryResult.total_success }}
        </span>
      </div>
      <div v-if="queryable" class="trend-query">
        <el-date-picker
          v-model="queryMonth"
          type="month"
          placeholder="选择历史月"
          value-format="YYYY-MM"
          size="small"
          :disabled-date="disableFutureOrCurrent"
          style="width: 130px"
        />
        <el-button size="small" type="primary" :disabled="!queryMonth" @click="emit('query', queryMonth)">查询</el-button>
      </div>
    </div>
    <div class="trend-total">{{ total }}</div>
    <div ref="chartEl" class="trend-chart"></div>
  </el-card>
</template>

<style scoped>
.trend-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.trend-head-left { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.trend-title { font-size: 14px; font-weight: 600; color: #606266; }
.trend-query { display: flex; align-items: center; gap: 6px; }
.trend-total { font-size: 28px; font-weight: 600; color: #303133; margin: 6px 0 4px; }
.trend-query-result { font-size: 14px; font-weight: 600; color: #606266; }
.trend-chart { height: 180px; width: 100%; }
</style>
