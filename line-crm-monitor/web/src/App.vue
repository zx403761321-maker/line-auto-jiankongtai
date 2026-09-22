<script setup>
import { ref } from 'vue'
import { setUnauthorizedHandler, logout } from './api'
import LoginDialog from './components/LoginDialog.vue'

const showLogin = ref(false)

setUnauthorizedHandler(() => {
  showLogin.value = true
})

function onLoginSuccess() {
  showLogin.value = false
  // 登录后整页刷新，触发各页面重新拉取数据
  window.location.reload()
}

async function doLogout() {
  try {
    await logout()
  } catch (e) {
    // 忽略登出失败
  }
  window.location.reload()
}
</script>

<template>
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="logo">LINE CRM 监控</div>
      <el-menu
        :default-active="$route.path"
        router
        background-color="#1f2d3d"
        text-color="#bfcbd9"
        active-text-color="#409eff"
      >
        <el-menu-item index="/overview">首页总览</el-menu-item>
        <el-menu-item index="/servers">服务器列表</el-menu-item>
        <el-menu-item index="/devices">设备列表</el-menu-item>
        <el-menu-item index="/alerts">异常中心</el-menu-item>
        <el-menu-item index="/tasks">Task中心</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span>中央监控 Dashboard</span>
        <el-button size="small" @click="doLogout">登出</el-button>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <LoginDialog v-model="showLogin" @success="onLoginSuccess" />
</template>

<style>
html,
body,
#app {
  height: 100%;
  margin: 0;
}
.layout {
  height: 100%;
}
.aside {
  background-color: #1f2d3d;
}
.logo {
  color: #fff;
  font-size: 16px;
  padding: 16px;
  text-align: center;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e6e6e6;
}
</style>
