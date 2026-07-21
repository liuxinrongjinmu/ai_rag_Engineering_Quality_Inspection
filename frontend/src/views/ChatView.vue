<!--
  智能问答页面
  核心问答交互界面：消息列表、流式输出、来源追溯
-->
<template>
  <div class="chat-view">
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
        :disabled="isLoading"
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
import ChatMessage from '../components/ChatMessage.vue'
import ChatInput from '../components/ChatInput.vue'
import SourceCard from '../components/SourceCard.vue'
import SourceDetail from '../components/SourceDetail.vue'
import QuickQuestions from '../components/QuickQuestions.vue'
import { streamQuery } from '../api'

/* ==================== 响应式状态 ==================== */

/**
 * 消息列表
 * 每条消息: { role, content, sources, queryTimeMs, isStreaming }
 */
const messages = ref([])

/**
 * 加载状态（正在等待 AI 回复）
 */
const isLoading = ref(false)

/**
 * 当前 SSE 请求的 AbortController，用于中断请求
 */
let currentAbortController = null

/**
 * 滚动条组件引用
 */
const scrollbarRef = ref(null)

/**
 * 当前查看详情的切片 ID
 */
const selectedChunkId = ref('')

/* ==================== 滚动控制 ==================== */

/**
 * 滚动到底部
 */
async function scrollToBottom() {
  await nextTick()
  const wrap = scrollbarRef.value?.wrapRef
  if (wrap) {
    wrap.scrollTop = wrap.scrollHeight
  }
}

/**
 * 监听消息列表变化，自动滚动到底部
 */
watch(
  () => messages.value.length,
  () => scrollToBottom()
)

/**
 * 监听流式内容更新，平滑滚动
 */
watch(
  () => {
    const last = messages.value[messages.value.length - 1]
    return last?.content
  },
  () => scrollToBottom()
)

/* ==================== 核心交互 ==================== */

/**
 * 处理发送消息
 * @param {Object} payload - { question, useWebSearch }
 */
function handleSend({ question, useWebSearch }) {
  // 中断正在进行的请求
  if (currentAbortController) {
    currentAbortController.abort()
    currentAbortController = null
    // 修复中断状态：将最后一条助手消息标记为非流式
    const lastMsg = messages.value[messages.value.length - 1]
    if (lastMsg && lastMsg.role === 'assistant' && lastMsg.isStreaming) {
      lastMsg.isStreaming = false
      if (!lastMsg.content) {
        lastMsg.content = '回答已中断。'
      }
    }
    isLoading.value = false
  }

  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: question,
    sources: [],
    queryTimeMs: 0,
    isStreaming: false,
  })

  // 添加占位的助手消息（流式填充）
  const assistantIndex = messages.value.length
  messages.value.push({
    role: 'assistant',
    content: '',
    sources: [],
    queryTimeMs: 0,
    isStreaming: true,
  })

  isLoading.value = true

  // 发起 SSE 流式请求
  currentAbortController = streamQuery(
    { question, useWebSearch },
    {
      /**
       * 收到每个 token 时的回调
       */
      onToken(token) {
        const msg = messages.value[assistantIndex]
        if (msg) {
          msg.content += token
        }
      },

      /**
       * 回答完成时的回调
       */
      onDone({ sources, queryTimeMs, usedWebSearch, cached }) {
        const msg = messages.value[assistantIndex]
        if (msg) {
          msg.sources = sources
          msg.queryTimeMs = queryTimeMs
          msg.isStreaming = false
        }
        isLoading.value = false
        currentAbortController = null

        if (cached) {
          ElMessage.success('命中缓存，响应已加速')
        }
      },

      /**
       * 发生错误时的回调
       */
      onError(error) {
        const msg = messages.value[assistantIndex]
        if (msg) {
          msg.content = `抱歉，回答生成失败：${error.message || '未知错误'}`
          msg.isStreaming = false
        }
        isLoading.value = false
        currentAbortController = null

        ElMessage.error('回答生成失败，请稍后重试')
      },
    }
  )
}

/**
 * 处理快捷问题点击
 * @param {string} question - 问题文本
 */
function handleQuickQuestion(question) {
  handleSend({ question, useWebSearch: false })
}

/**
 * 打开来源详情
 * @param {string} chunkId - 切片 ID
 */
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

/* ==================== 滚动区域 ==================== */
.chat-scrollbar {
  flex: 1;
  overflow: hidden;
}

.chat-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px 20px;
  min-height: 100%;
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
