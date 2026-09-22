<script setup>
import { ref } from 'vue'
import { login } from '../api'

defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'success'])

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  if (!username.value || !password.value) return
  loading.value = true
  error.value = ''
  try {
    await login(username.value, password.value)
    username.value = ''
    password.value = ''
    emit('success')
  } catch (e) {
    error.value = '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="登录"
    width="360px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
  >
    <el-input
      v-model="username"
      placeholder="用户名"
      @keyup.enter="submit"
    />
    <el-input
      v-model="password"
      type="password"
      placeholder="密码"
      show-password
      class="mt"
      @keyup.enter="submit"
    />
    <div v-if="error" class="error">{{ error }}</div>
    <template #footer>
      <el-button type="primary" :loading="loading" @click="submit">登录</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.mt {
  margin-top: 12px;
}
.error {
  color: #f56c6c;
  font-size: 12px;
  margin-top: 8px;
}
</style>
