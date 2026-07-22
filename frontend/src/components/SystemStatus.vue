<!--
  系统状态组件
  展示各组件的健康状态和知识库统计信息，支持自动刷新
-->
<template>
  <div class="system-status">
    <div class="section-header">
      <h3>系统状态</h3>
      <div class="header-actions">
        <el-button :icon="Refresh" size="small" :loading="loading" @click="fetchHealth">
          刷新
        </el-button>
        <el-popconfirm
          title="增量同步仅处理变更文档，未变化文档跳过，是否继续？"
          confirm-button-text="确认"
          cancel-button-text="取消"
          @confirm="$emit('sync')"
        >
          <template #reference>
            <el-button type="success" size="small" :icon="RefreshRight">
              增量同步
            </el-button>
          </template>
        </el-popconfirm>
        <el-popconfirm
          title="重建知识库将重新处理所有文档，此操作不可撤销，确认继续？"
          confirm-button-text="确认"
          cancel-button-text="取消"
          @confirm="$emit('rebuild')"
        >
          <template #reference>
            <el-button type="warning" size="small" :icon="RefreshRight">
              全量重建
            </el-button>
          </template>
        </el-popconfirm>
      </div>
    </div>

    <!-- 组件状态 -->
    <el-card shadow="never" class="status-card">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="系统状态">
          <el-tag :type="statusType" size="small" effect="dark">
            {{ statusText }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="向量数据库">
          <div class="component-status">
            <span class="status-dot" :class="getComponentClass('vectordb')"></span>
            {{ componentLabel('vectordb') }}
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="LLM">
          <div class="component-status">
            <span class="status-dot" :class="getComponentClass('llm')"></span>
            {{ componentLabel('llm') }}
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="Embedding">
          <div class="component-status">
            <span class="status-dot" :class="getComponentClass('embedder')"></span>
            {{ componentLabel('embedder') }}
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="总切片数">
          <span class="stat-value">{{ stats.total_chunks ?? '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="总文档数">
          <span class="stat-value">{{ stats.total_docs ?? '-' }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 加载错误 -->
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      class="error-alert"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getHealth } from '../api'

/**
 * Emits 定义
 */
defineEmits(['rebuild', 'sync'])

/**
 * 加载状态
 */
const loading = ref(false)

/**
 * 错误信息
 */
const error = ref('')

/**
 * 健康状态数据
 */
const status = ref('unknown')
const components = ref({})
const stats = ref({})

/**
 * 自动刷新定时器
 */
let refreshTimer = null

/**
 * 系统状态文本
 */
const statusText = computed(() => {
  const map = {
    healthy: '正常',
    degraded: '降级',
    unknown: '未知',
  }
  return map[status.value] || status.value
})

/**
 * 系统状态标签类型
 */
const statusType = computed(() => {
  const map = {
    healthy: 'success',
    degraded: 'danger',
    unknown: 'info',
  }
  return map[status.value] || 'info'
})

/**
 * 获取组件状态的 CSS 类名
 * @param {string} name - 组件名
 * @returns {string} CSS 类名
 */
function getComponentClass(name) {
  const state = components.value[name] || 'unknown'
  const map = {
    ok: 'status-healthy',
    error: 'status-error',
    unknown: 'status-unknown',
  }
  return map[state] || 'status-unknown'
}

/**
 * 获取组件状态的显示文本
 * @param {string} name - 组件名
 * @returns {string} 状态文本
 */
function componentLabel(name) {
  const state = components.value[name] || 'unknown'
  const map = {
    ok: '正常',
    error: '异常',
    unknown: '未知',
  }
  return map[state] || state
}

/**
 * 获取系统健康状态
 */
async function fetchHealth() {
  loading.value = true
  error.value = ''

  try {
    const res = await getHealth()
    // 兼容两种响应格式：{ status, components, stats } 或 { data: { ... } }
    const data = res.data || res
    status.value = data.status || 'unknown'
    components.value = data.components || {}
    stats.value = data.stats || {}
  } catch (err) {
    error.value = err.message || '获取系统状态失败'
    console.error('[SystemStatus] 获取状态失败:', err)
  } finally {
    loading.value = false
  }
}

/**
 * 组件挂载时：获取状态并启动定时刷新
 */
onMounted(() => {
  fetchHealth()
  refreshTimer = setInterval(fetchHealth, 30000) // 30秒刷新一次
})

/**
 * 组件卸载时：清除定时器
 */
onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
/* ==================== 头部 ==================== */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  gap: 8px;
}

/* ==================== 状态卡片 ==================== */
.status-card {
  border-radius: 8px;
}

/* ==================== 组件状态指示 ==================== */
.component-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}

.status-healthy {
  background: #67c23a;
  box-shadow: 0 0 4px rgba(103, 194, 58, 0.4);
}

.status-error {
  background: #f56c6c;
  box-shadow: 0 0 4px rgba(245, 108, 108, 0.4);
}

.status-unknown {
  background: #c0c4cc;
}

/* ==================== 统计数值 ==================== */
.stat-value {
  font-weight: 600;
  color: var(--primary-color);
}

/* ==================== 错误提示 ==================== */
.error-alert {
  margin-top: 12px;
}
</style>
