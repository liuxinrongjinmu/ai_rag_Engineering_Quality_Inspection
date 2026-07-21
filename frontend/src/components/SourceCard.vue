<!--
  来源卡片组件
  展示单个检索来源的基本信息，区分本地文档和网络来源
-->
<template>
  <div class="source-card">
    <div class="source-header">
      <!-- 来源类型标签 -->
      <el-tag
        :type="isWeb ? 'warning' : 'success'"
        size="small"
        effect="plain"
        class="source-tag"
      >
        {{ isWeb ? '网络来源' : '规范文档' }}
      </el-tag>

      <!-- 文档名称 -->
      <span class="source-doc-name" :title="source.doc_name || '未知文档'">
        {{ source.doc_name || '未知文档' }}
      </span>
    </div>

    <!-- 页码 / 章节信息 -->
    <div v-if="source.page || source.section" class="source-location">
      <el-icon :size="14"><Location /></el-icon>
      <span v-if="source.section">第{{ source.section }}节</span>
      <span v-if="source.page && source.section"> · </span>
      <span v-if="source.page">第{{ source.page }}页</span>
    </div>

    <!-- 内容预览 -->
    <div class="source-preview">
      {{ truncateContent(source.content) }}
    </div>

    <!-- 操作区 -->
    <div class="source-footer">
      <el-button
        type="primary"
        link
        size="small"
        @click="$emit('view-detail', source.chunk_id)"
      >
        <el-icon><View /></el-icon>
        查看原文
      </el-button>
      <a
        v-if="isWeb && source.url"
        :href="source.url"
        target="_blank"
        rel="noopener noreferrer"
        class="source-url-link"
      >
        <el-icon><Link /></el-icon>
        原始链接
      </a>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

/**
 * Props 定义
 */
const props = defineProps({
  /** 来源对象 */
  source: {
    type: Object,
    required: true,
  },
})

/**
 * Emits 定义
 */
defineEmits(['view-detail'])

/**
 * 是否为网络来源
 */
const isWeb = computed(() => {
  return props.source.source_type === 'web'
})

/**
 * 截断过长的内容预览
 * @param {string} content - 原始内容
 * @returns {string} 截断后的内容
 */
function truncateContent(content) {
  if (!content) return ''
  if (content.length <= 120) return content
  return content.slice(0, 120) + '...'
}
</script>

<style scoped>
.source-card {
  background: #fff;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 12px;
  transition: box-shadow 0.2s;
}

.source-card:hover {
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.08);
}

/* ==================== 来源头部 ==================== */
.source-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.source-tag {
  flex-shrink: 0;
  font-size: 11px;
}

.source-doc-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ==================== 位置信息 ==================== */
.source-location {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

/* ==================== 内容预览 ==================== */
.source-preview {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ==================== 底部操作 ==================== */
.source-footer {
  display: flex;
  align-items: center;
  gap: 12px;
}

.source-url-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  text-decoration: none;
}

.source-url-link:hover {
  color: var(--primary-color);
}
</style>
