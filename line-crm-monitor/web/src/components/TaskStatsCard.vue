<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  success: { type: Number, default: 0 },
  fail: { type: Number, default: 0 },
  failedDevices: { type: Number, default: 0 },
})

const R = 50
const C = 2 * Math.PI * R
const donut = computed(() => {
  const total = props.success + props.fail
  const successLen = total > 0 ? (props.success / total) * C : 0
  const failLen = total > 0 ? (props.fail / total) * C : 0
  const rateText = total > 0 ? `${Math.round((props.success / total) * 100)}%` : '—'
  return { successLen, failLen, rateText }
})
</script>

<template>
  <el-card shadow="hover">
    <div class="task-title">{{ title }}</div>
    <div class="task-viz">
      <svg viewBox="0 0 120 120" class="donut">
        <circle cx="60" cy="60" :r="R" fill="none" stroke="#ebeef5" stroke-width="16" />
        <circle
          v-if="donut.successLen > 0"
          cx="60" cy="60" :r="R" fill="none" stroke="#67c23a" stroke-width="16"
          :stroke-dasharray="`${donut.successLen} ${C}`" transform="rotate(-90 60 60)"
        />
        <circle
          v-if="donut.failLen > 0"
          cx="60" cy="60" :r="R" fill="none" stroke="#f56c6c" stroke-width="16"
          :stroke-dasharray="`${donut.failLen} ${C}`" :stroke-dashoffset="-donut.successLen"
          transform="rotate(-90 60 60)"
        />
        <text x="60" y="57" text-anchor="middle" class="donut-rate">{{ donut.rateText }}</text>
        <text x="60" y="75" text-anchor="middle" class="donut-label">成功率</text>
      </svg>
      <div class="task-nums">
        <div class="task-num">
          <div class="num-label">成功数量</div>
          <div class="num-value ok">{{ success }}</div>
        </div>
        <div class="task-num">
          <div class="num-label">失败数量</div>
          <div class="num-value bad">{{ fail }}</div>
        </div>
        <div class="task-num">
          <div class="num-label">失败设备数量</div>
          <div class="num-value">{{ failedDevices }}</div>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.task-title { font-size: 14px; font-weight: 600; color: #606266; margin-bottom: 12px; }
.task-viz { display: flex; align-items: center; gap: 40px; }
.donut { width: 150px; height: 150px; flex-shrink: 0; }
.donut-rate { font-size: 22px; font-weight: 700; fill: #303133; }
.donut-label { font-size: 12px; fill: #909399; }
.task-nums { display: flex; gap: 40px; }
.task-num { text-align: center; }
.num-label { color: #909399; font-size: 13px; }
.num-value { font-size: 26px; font-weight: 600; margin-top: 6px; }
.num-value.ok { color: #67c23a; }
.num-value.bad { color: #f56c6c; }
</style>
