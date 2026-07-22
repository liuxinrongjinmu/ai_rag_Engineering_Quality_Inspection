<!--
  智能问答页面
  核心问答交互界面：消息列表、流式输出、来源追溯
  会话历史跨路由保持
-->
<template>
  <div class="chat-view">
    <!-- 顶部工具栏 -->
    <div class="chat-toolbar" v-if="messages.length > 0">
      <span class="toolbar-title">智能问答</span>
      <el-button
        :icon="PlusIcon"
        type="primary"
        plain
        size="small"
        @click="handleNewChat"
        :disabled="$chat.isLoading"
      >
        新会话
      </el-button>
    </div>

    <!-- 对话滚动区域 -->
    <el-scrollbar ref="scrollbarRef" class="chat-scrollbar" always>
      <div class="chat-container">
        <!-- 欢迎状态：无消息时显示引导 -->
        <div v-if="messages.length === 0" class="welcome-state">
          <div class="welcome-logo">
            <el-avatar :size="72" :icon="ChatDotRound" class="welcome-avatar" />
          </div>
          <h2 class="welcome-title">工程质检智能问答</h2>
          <p class="welcome-desc">
            基于公路工程相关规范和标准，为您提供专业的质量检测知识问答服务
          </p>
          <QuickQuestions @select="handleQuickQuestion" />
        </div>

        <!-- 消息列表 -->
        <div v-else class="message-list">
          <ChatMessage
            v-for="(msg, index) in messages"
            :key="index"
            :role="msg.role"
            :content="msg.content"
            :sources="msg.sources"
            :query-time-ms="msg.queryTimeMs"
            :is-streaming="msg.isStreaming"
          >
            <!-- 来源卡片插槽 -->
            <template #sources="{ sources: msgSources }">
              <SourceCard
                v-for="src in msgSources"
                :key="src.chunk_id"
                :source="src"
                @view-detail="openSourceDetail"
              />
            </template>
          </ChatMessage>
        </div>
      </div>
    </el-scrollbar>

    <!-- 底部输入区 -->
    <div class="chat-footer">
      <ChatInput
        :disabled="$chat.isLoading"
        @send="handleSend"
      />

      <!-- 快速问题（消息列表已有内容时显示在底部） -->
      <div v-if="messages.length > 0" class="footer-quick-questions">
        <QuickQuestions @select="handleQuickQuestion" />
      </div>
    </div>

    <!-- 来源详情弹窗 -->
    <SourceDetail :chunk-id="selectedChunkId" />
  </div>
</template>

<script setup>
import { ref, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, ChatDotRound } from '@element-plus/icons-vue'
import ChatMessage from '../components/ChatMessage.vue'
import ChatInput from '../components/ChatInput.vue'
import SourceCard from '../components/SourceCard.vue'
import SourceDetail from '../components/SourceDetail.vue'
import QuickQuestions from '../components/QuickQuestions.vue'
import { streamQuery } from '../api'
import { useChatStore } from '../stores/chat'

/* ==================== 共享状态（跨路由保持） ==================== */
const { state: $chat, newChat, addMessage, abortCurrentRequest } = useChatStore()

/* ==================== 滚动条组件引用 ==================== */
const scrollbarRef = ref(null)

/* ==================== 来源详情 ==================== */
const selectedChunkId = ref('')

/* ==================== 便捷计算属性 ==================== */

// 直接引用共享状态中的 messages 和 isLoading，在模板中和 tooltip 中使用
const messages = $chat.messages
// 注意：模板中直接使用 $chat.isLoading，此处不再单独声明 isLoading 变量

/* ==================== ElMessage 图标 ==================== */
const PlusIcon = Plus

/* ==================== 滚动控制 ==================== */

async function scrollToBottom() {
  await nextTick()
  const wrap = scrollbarRef.value?.wrapRef
  if (wrap) {
    wrap.scrollTop = wrap.scrollHeight
  }
}

watch(() => messages.length, () => scrollToBottom())

watch(
  () => {
    const last = messages[messages.length - 1]
    return last?.content
  },
  () => scrollToBottom()
)

/* ==================== 核心交互 ==================== */

function handleSend({ question, useWebSearch }) {
  // 中断正在进行的请求
  abortCurrentRequest()

  // 添加用户消息
  addMessage({
    role: 'user',
    content: question,
    sources: [],
    queryTimeMs: 0,
    isStreaming: false,
  })

  // 添加占位的助手消息（流式填充）
  const assistantIndex = messages.length
  addMessage({
    role: 'assistant',
    content: '',
    sources: [],
    queryTimeMs: 0,
    isStreaming: true,
  })

  $chat.isLoading = true

  // 发起 SSE 流式请求
  const abortCtrl = streamQuery(
    { question, useWebSearch },
    {
      onToken(token) {
        const msg = messages[assistantIndex]
        if (msg) {
          msg.content += token
        }
      },
      onDone({ sources, queryTimeMs, usedWebSearch, cached }) {
        const msg = messages[assistantIndex]
        if (msg) {
          msg.sources = sources
          msg.queryTimeMs = queryTimeMs
          msg.isStreaming = false
        }
        $chat.isLoading = false
        $chat.currentAbortController = null

        if (cached) {
          ElMessage.success('命中缓存，响应已加速')
        }
      },
      onError(error) {
        const msg = messages[assistantIndex]
        if (msg) {
          msg.content = `抱歉，回答生成失败：${error.message || '未知错误'}`
          msg.isStreaming = false
        }
        $chat.isLoading = false
        $chat.currentAbortController = null

        ElMessage.error('回答生成失败，请稍后重试')
      },
    }
  )
  $chat.currentAbortController = abortCtrl
}

function handleQuickQuestion(question) {
  handleSend({ question, useWebSearch: false })
}

function handleNewChat() {
  newChat()
}

function openSourceDetail(chunkId) {
  selectedChunkId.value = chunkId
}
</script>

<style scoped>
/* ==================== 整体布局 ==================== */
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-color);
}

/* ==================== 顶部工具栏 ==================== */
.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  background: #fff;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.toolbar-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

/* ==================== 滚动区域 ==================== */
.chat-scrollbar {
  flex: 1;
  overflow: hidden;
}

.chat-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px 20px;
  min-height: calc(100% - 56px);
  display: flex;
  flex-direction: column;
}

/* ==================== 欢迎状态 ==================== */
.welcome-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 0;
  text-align: center;
}

.welcome-logo {
  margin-bottom: 20px;
}

.welcome-avatar {
  background: linear-gradient(135deg, #409eff, #67c23a);
}

.welcome-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.welcome-desc {
  font-size: 14px;
  color: var(--text-secondary);
  max-width: 400px;
  line-height: 1.6;
  margin-bottom: 8px;
}

/* ==================== 消息列表 ==================== */
.message-list {
  flex: 1;
  padding-bottom: 20px;
}

/* ==================== 底部区域 ==================== */
.chat-footer {
  flex-shrink: 0;
}

.footer-quick-questions {
  background: #f5f7fa;
  border-top: 1px solid var(--border-color);
}

.footer-quick-questions :deep(.quick-questions) {
  padding: 10px 0;
}

/* ==================== 响应式 ==================== */
@media (max-width: 768px) {
  .chat-container {
    max-width: 100%;
    padding: 12px;
  }

  .welcome-title {
    font-size: 20px;
  }
}
</style>
