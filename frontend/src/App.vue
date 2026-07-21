<template>
  <el-container class="app-container">
    <el-header class="app-header">
      <div class="header-left">
        <el-icon :size="24"><Monitor /></el-icon>
        <span class="header-title">工程质检RAG系统</span>
      </div>
      <div class="header-right">
        <router-link to="/" class="nav-link" :class="{ active: $route.path === '/' }">
          <el-icon><ChatDotRound /></el-icon>
          <span>智能问答</span>
        </router-link>
        <router-link to="/admin" class="nav-link" :class="{ active: $route.path === '/admin' }">
          <el-icon><Setting /></el-icon>
          <span>管理后台</span>
        </router-link>
      </div>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
</script>

<style>
:root {
  --primary-color: #409eff;
  --bg-color: #f5f7fa;
  --header-bg: #2c3e50;
  --user-msg-bg: #409eff;
  --assistant-msg-bg: #ffffff;
  --border-color: #e4e7ed;
  --text-primary: #303133;
  --text-secondary: #909399;
}

body {
  background-color: var(--bg-color);
}

.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  background: var(--header-bg);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 1px;
}

.header-right {
  display: flex;
  gap: 8px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 6px;
  color: rgba(255,255,255,0.7);
  text-decoration: none;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s;
}

.nav-link:hover,
.nav-link.active {
  color: #fff;
  background: rgba(255,255,255,0.15);
}

.app-main {
  flex: 1;
  overflow: hidden;
  padding: 0;
}
</style>
