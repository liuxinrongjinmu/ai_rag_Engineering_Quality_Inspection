<!--
  404 页面
  路由未匹配时显示
-->
<template>
  <div class="not-found">
    <div class="not-found-content">
      <h1 class="not-found-code">404</h1>
      <p class="not-found-text">页面不存在</p>
      <el-button type="primary" @click="$router.push('/')">
        返回首页
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  background: var(--bg-color);
}

.not-found-content {
  text-align: center;
}

.not-found-code {
  font-size: 72px;
  font-weight: 700;
  color: #c0c4cc;
  margin: 0 0 12px;
}

.not-found-text {
  font-size: 16px;
  color: var(--text-secondary);
  margin-bottom: 24px;
}
</style>
