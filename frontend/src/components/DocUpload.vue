<!--
  文档上传组件
  支持拖拽上传多格式文件（MD/PDF/Word/TXT/Excel），显示上传进度
-->
<template>
  <div class="doc-upload">
    <div class="section-header">
      <h3>上传文档</h3>
      <span class="upload-hint">支持 .md / .txt / .pdf / .docx / .xls / .xlsx</span>
    </div>

    <el-upload
      class="upload-area"
      drag
      action="/api/v1/admin/documents/upload"
      :accept="'.md,.txt,.pdf,.docx,.xls,.xlsx'"
      :auto-upload="true"
      :show-file-list="true"
      :limit="5"
      :on-success="handleSuccess"
      :on-error="handleError"
      :on-progress="handleProgress"
      :before-upload="beforeUpload"
      name="file"
    >
      <el-icon class="upload-icon"><UploadFilled /></el-icon>
      <div class="upload-text">
        <p>将文件拖到此处，或 <em>点击上传</em></p>
        <p class="upload-sub">支持 .md / .txt / .pdf / .docx / .xls / .xlsx</p>
      </div>
    </el-upload>
  </div>
</template>

<script setup>
import { ElMessage } from 'element-plus'

/**
 * Emits 定义
 */
const emit = defineEmits(['uploaded'])

/**
 * 上传前的校验
 * @param {File} file - 待上传的文件
 * @returns {boolean} 是否允许上传
 */
function beforeUpload(file) {
  const allowedExtensions = ['.md', '.txt', '.pdf', '.docx', '.xls', '.xlsx']
  const ext = '.' + file.name.split('.').pop().toLowerCase()

  if (!allowedExtensions.includes(ext)) {
    ElMessage.warning(`不支持的文件格式: ${file.name}，仅支持 .md / .txt / .pdf / .docx / .xls / .xlsx`)
    return false
  }

  // 限制文件大小 50MB
  const maxSize = 50 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.warning(`文件过大: ${file.name}，最大支持 50MB`)
    return false
  }

  return true
}

/**
 * 上传进度回调
 */
function handleProgress(event, file) {
  // el-upload 自带进度条，无需额外处理
}

/**
 * 上传成功回调
 */
function handleSuccess(response, file) {
  ElMessage.success(`${file.name} 上传成功`)
  emit('uploaded')
}

/**
 * 上传失败回调
 */
function handleError(error, file) {
  ElMessage.error(`${file.name} 上传失败: ${error.message || '未知错误'}`)
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

.upload-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

/* ==================== 上传区域 ==================== */
.upload-area {
  width: 100%;
}

.upload-area :deep(.el-upload-dragger) {
  padding: 32px 20px;
  border: 2px dashed #d9dde4;
  border-radius: 12px;
  transition: all 0.2s;
}

.upload-area :deep(.el-upload-dragger:hover) {
  border-color: var(--primary-color);
  background: #f8faff;
}

.upload-icon {
  font-size: 40px;
  color: #c0c4cc;
  margin-bottom: 8px;
}

.upload-text p {
  font-size: 14px;
  color: #606266;
  margin: 4px 0;
}

.upload-text em {
  color: var(--primary-color);
  font-style: normal;
  cursor: pointer;
}

.upload-sub {
  font-size: 12px !important;
  color: var(--text-secondary) !important;
}
</style>
