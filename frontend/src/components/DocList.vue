<!--
  文档列表组件
  以表格形式展示已上传文档，支持删除操作
-->
<template>
  <div class="doc-list">
    <div class="section-header">
      <h3>文档列表</h3>
      <span class="doc-count">共 {{ documents.length }} 个文档</span>
    </div>

    <el-table
      :data="documents"
      style="width: 100%"
      empty-text="暂无文档"
      :header-cell-style="{ background: '#f5f7fa', fontWeight: 600 }"
    >
      <!-- 文档名 -->
      <el-table-column label="文档名" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">
          <div class="doc-name-cell">
            <el-icon :size="16"><Document /></el-icon>
            <span>{{ row.doc_name }}</span>
          </div>
        </template>
      </el-table-column>

      <!-- 类型 -->
      <el-table-column label="类型" width="110" align="center">
        <template #default="{ row }">
          <el-tag
            :type="getTypeTagType(row.doc_type)"
            size="small"
            effect="light"
          >
            {{ formatDocType(row.doc_type) }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 切片数 -->
      <el-table-column label="切片数" width="100" align="center">
        <template #default="{ row }">
          <span class="chunk-count">{{ row.chunk_count ?? '-' }}</span>
        </template>
      </el-table-column>

      <!-- 操作 -->
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row }">
          <el-popconfirm
            title="确认删除该文档？"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="$emit('delete', row.doc_id)"
          >
            <template #reference>
              <el-button type="danger" link size="small">
                <el-icon><Delete /></el-icon>
                删除
              </el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
/**
 * Props 定义
 */
defineProps({
  /** 文档数组 */
  documents: {
    type: Array,
    default: () => [],
  },
})

/**
 * Emits 定义
 */
defineEmits(['delete'])

/**
 * 格式化文档类型显示文本
 * @param {string} type - 文档类型
 * @returns {string} 格式化后的类型名
 */
function formatDocType(type) {
  const map = {
    pdf: 'PDF',
    markdown: 'Markdown',
    excel: 'Excel',
    xls: 'Excel',
    xlsx: 'Excel',
  }
  return map[type] || type || '未知'
}

/**
 * 根据文档类型返回 Element Plus tag type
 * @param {string} type - 文档类型
 * @returns {string} Element Plus type 值
 */
function getTypeTagType(type) {
  const map = {
    pdf: 'danger',
    markdown: 'primary',
    excel: 'success',
    xls: 'success',
    xlsx: 'success',
  }
  return map[type] || 'info'
}
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

.doc-count {
  font-size: 13px;
  color: var(--text-secondary);
}

/* ==================== 单元格 ==================== */
.doc-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.doc-name-cell .el-icon {
  flex-shrink: 0;
  color: var(--primary-color);
}

.chunk-count {
  font-weight: 500;
  color: var(--text-primary);
}
</style>
