<!--
  管理后台页面
  文档管理 + 系统状态监控，侧边栏导航切换
-->
<template>
  <el-container class="admin-view">
    <!-- 侧边栏 -->
    <el-aside width="220px" class="admin-aside">
      <el-menu
        :default-active="activeMenu"
        class="admin-menu"
        @select="handleMenuSelect"
      >
        <el-menu-item index="documents">
          <el-icon><Document /></el-icon>
          <span>文档管理</span>
        </el-menu-item>
        <el-menu-item index="status">
          <el-icon><Monitor /></el-icon>
          <span>系统状态</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 主内容区 -->
    <el-main class="admin-main">
      <!-- 文档管理 -->
      <div v-if="activeMenu === 'documents'" class="content-panel">
        <DocUpload @uploaded="fetchDocuments" />

        <el-divider />

        <DocList
          :documents="documents"
          @delete="handleDeleteDocument"
        />
      </div>

      <!-- 系统状态 -->
      <div v-else-if="activeMenu === 'status'" class="content-panel">
        <SystemStatus @rebuild="handleRebuild" @sync="handleSync" />
      </div>
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import DocList from '../components/DocList.vue'
import DocUpload from '../components/DocUpload.vue'
import SystemStatus from '../components/SystemStatus.vue'
import { getDocuments, deleteDocument, rebuildKnowledge, syncKnowledge } from '../api'

/* ==================== 状态 ==================== */

/**
 * 当前激活的菜单项
 */
const activeMenu = ref('documents')

/**
 * 文档列表
 */
const documents = ref([])

/* ==================== 菜单切换 ==================== */

/**
 * 处理菜单选择
 * @param {string} index - 菜单项 index
 */
function handleMenuSelect(index) {
  activeMenu.value = index
}

/* ==================== 文档管理 ==================== */

/**
 * 获取文档列表
 */
async function fetchDocuments() {
  try {
    const res = await getDocuments()
    // 兼容不同响应格式
    const data = res.data || res
    documents.value = Array.isArray(data) ? data : (data.documents || data.items || [])
  } catch (err) {
    ElMessage.error('获取文档列表失败: ' + (err.message || '未知错误'))
    console.error('[AdminView] 获取文档列表失败:', err)
  }
}

/**
 * 删除文档
 * @param {string} docId - 文档 ID
 */
async function handleDeleteDocument(docId) {
  try {
    await deleteDocument(docId)
    ElMessage.success('文档已删除')
    await fetchDocuments()
  } catch (err) {
    ElMessage.error('删除文档失败: ' + (err.message || '未知错误'))
    console.error('[AdminView] 删除文档失败:', err)
  }
}

/* ==================== 系统状态 ==================== */

/**
 * 重建知识库
 */
async function handleRebuild() {
  try {
    ElMessage.info('正在重建知识库，请稍候...')
    await rebuildKnowledge()
    ElMessage.success('知识库重建完成')
  } catch (err) {
    ElMessage.error('重建知识库失败: ' + (err.message || '未知错误'))
    console.error('[AdminView] 重建知识库失败:', err)
  }
}

/**
 * 增量同步知识库
 */
async function handleSync() {
  try {
    ElMessage.info('正在增量同步知识库，请稍候...')
    const res = await syncKnowledge()
    const data = res.data || res
    const { new_count, modified_count, deleted_count, unchanged_count, total_chunks_added } = data
    if (new_count === 0 && modified_count === 0 && deleted_count === 0) {
      ElMessage.success(`知识库已是最新（${unchanged_count}个文件无变更）`)
    } else {
      const parts = []
      if (new_count > 0) parts.push(`新增${new_count}个`)
      if (modified_count > 0) parts.push(`修改${modified_count}个`)
      if (deleted_count > 0) parts.push(`删除${deleted_count}个`)
      ElMessage.success(`增量同步完成: ${parts.join('、')}，共${total_chunks_added}个切片`)
    }
  } catch (err) {
    ElMessage.error('增量同步失败: ' + (err.message || '未知错误'))
    console.error('[AdminView] 增量同步失败:', err)
  }
}

/* ==================== 生命周期 ==================== */

/**
 * 组件挂载时加载文档列表
 */
onMounted(() => {
  fetchDocuments()
})
</script>

<style scoped>
/* ==================== 整体布局 ==================== */
.admin-view {
  height: 100%;
  background: var(--bg-color);
}

/* ==================== 侧边栏 ==================== */
.admin-aside {
  background: #fff;
  border-right: 1px solid var(--border-color);
  overflow-y: auto;
  flex-shrink: 0;
}

.admin-menu {
  border-right: none;
  padding-top: 8px;
}

.admin-menu :deep(.el-menu-item) {
  font-size: 14px;
  height: 48px;
  line-height: 48px;
}

.admin-menu :deep(.el-menu-item .el-icon) {
  font-size: 18px;
}

/* ==================== 主内容区 ==================== */
.admin-main {
  background: var(--bg-color);
  padding: 24px;
  overflow-y: auto;
}

.content-panel {
  max-width: 1000px;
}
</style>
