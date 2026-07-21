<!--
  来源详情弹窗组件
  展示切片的完整内容、上下文和元信息
-->
<template>
  <el-dialog
    v-model="dialogVisible"
    title="来源详情"
    width="680px"
    :close-on-click-modal="false"
    destroy-on-close
    class="source-detail-dialog"
  >
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p>正在加载来源详情...</p>
    </div>

    <!-- 加载失败 -->
    <div v-else-if="error" class="error-container">
      <el-result icon="error" :title="error" sub-title="请稍后重试" />
    </div>

    <!-- 详情内容 -->
    <template v-else-if="detail">
      <!-- 基本信息 -->
      <el-descriptions :column="2" border size="small" class="detail-descriptions">
        <el-descriptions-item label="文档名称" :span="2">
          {{ detail.doc_name || '未知' }}
        </el-descriptions-item>
        <el-descriptions-item label="页码">
          {{ detail.page ? `第${detail.page}页` : '无' }}
        </el-descriptions-item>
        <el-descriptions-item label="章节">
          {{ detail.section || '无' }}
        </el-descriptions-item>
      </el-descriptions>

      <!-- 前文上下文 -->
      <div v-if="detail.context_before" class="context-section">
        <div class="context-label">
          <el-icon><ArrowUp /></el-icon>
          <span>前文上下文</span>
        </div>
        <div class="context-content">{{ detail.context_before }}</div>
      </div>

      <!-- 主体内容 -->
      <div class="content-section">
        <div class="context-label highlight">
          <el-icon><Reading /></el-icon>
          <span>原文内容</span>
        </div>
        <div class="context-content full-content">{{ detail.full_content }}</div>
      </div>

      <!-- 后文上下文 -->
      <div v-if="detail.context_after" class="context-section">
        <div class="context-label">
          <el-icon><ArrowDown /></el-icon>
          <span>后文上下文</span>
        </div>
        <div class="context-content">{{ detail.context_after }}</div>
      </div>
    </template>

    <!-- 底部按钮 -->
    <template #footer>
      <div class="dialog-footer">
        <el-button
          v-if="detail"
          type="primary"
          :icon="copyIcon"
          @click="copyContent"
        >
          {{ copied ? '已复制' : '复制内容' }}
        </el-button>
        <el-button @click="dialogVisible = false">关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, shallowRef } from 'vue'
import { getSourceDetail } from '../api'

/**
 * Props 定义
 */
const props = defineProps({
  /** 切片 ID，传入非空值时自动加载详情并打开弹窗 */
  chunkId: {
    type: String,
    default: '',
  },
})

/**
 * 弹窗可见性
 */
const dialogVisible = ref(false)

/**
 * 加载状态
 */
const loading = ref(false)

/**
 * 错误信息
 */
const error = ref('')

/**
 * 详情数据
 */
const detail = shallowRef(null)

/**
 * 复制状态
 */
const copied = ref(false)

/**
 * 复制图标（切换显示）
 */
const copyIcon = ref('DocumentCopy')

/**
 * 监听 chunkId 变化，自动加载详情
 */
watch(
  () => props.chunkId,
  async (newId) => {
    if (!newId) {
      dialogVisible.value = false
      return
    }

    dialogVisible.value = true
    loading.value = true
    error.value = ''
    detail.value = null
    copied.value = false
    copyIcon.value = 'DocumentCopy'

    try {
      const res = await getSourceDetail(newId)
      detail.value = res.data || res
    } catch (err) {
      error.value = err.message || '加载来源详情失败'
      console.error('[SourceDetail] 加载失败:', err)
    } finally {
      loading.value = false
    }
  }
)

/**
 * 复制内容到剪贴板
 */
async function copyContent() {
  if (!detail.value) return

  const parts = []
  if (detail.value.doc_name) parts.push(`【文档】${detail.value.doc_name}`)
  if (detail.value.section) parts.push(`【章节】${detail.value.section}`)
  if (detail.value.page) parts.push(`【页码】第${detail.value.page}页`)
  if (detail.value.context_before) parts.push(`【前文】${detail.value.context_before}`)
  if (detail.value.full_content) parts.push(`【原文】${detail.value.full_content}`)
  if (detail.value.context_after) parts.push(`【后文】${detail.value.context_after}`)

  try {
    await navigator.clipboard.writeText(parts.join('\n\n'))
    copied.value = true
    copyIcon.value = 'Check'
    setTimeout(() => {
      copied.value = false
      copyIcon.value = 'DocumentCopy'
    }, 2000)
  } catch (err) {
    console.error('[SourceDetail] 复制失败:', err)
  }
}
</script>

<style scoped>
/* ==================== 加载 / 错误状态 ==================== */
.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
  color: var(--text-secondary);
  gap: 12px;
}

.error-container {
  padding: 24px 0;
}

/* ==================== el-descriptions ==================== */
.detail-descriptions {
  margin-bottom: 16px;
}

/* ==================== 上下文区域 ==================== */
.context-section {
  margin-bottom: 14px;
}

.context-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.context-label.highlight {
  color: var(--primary-color);
}

.context-content {
  background: #f8f9fb;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 14px;
  line-height: 1.8;
  color: #4a4a5a;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}

.context-content.full-content {
  max-height: none;
  background: #f0f9eb;
  border-color: #e1f3d8;
}

/* ==================== 底部按钮 ==================== */
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
