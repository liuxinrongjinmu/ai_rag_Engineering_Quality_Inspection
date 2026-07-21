<!--
  聊天消息组件
  支持用户消息（右对齐蓝色气泡）和助手消息（左对齐白色气泡）
  支持 Markdown 渲染和流式输出
-->
<template>
  <div class="chat-message" :class="role">
    <!-- 头像区域 -->
    <div class="message-avatar">
      <el-avatar :size="36" :style="{ background: role === 'user' ? 'var(--user-msg-bg)' : '#67c23a' }">
        <el-icon :size="20">
          <UserFilled v-if="role === 'user'" />
          <Monitor v-else />
        </el-icon>
      </el-avatar>
    </div>

    <!-- 消息主体 -->
    <div class="message-body">
      <!-- 发送者名称 -->
      <div class="message-meta">
        <span class="sender-name">{{ role === 'user' ? '我' : 'AI 助手' }}</span>
        <span v-if="role === 'assistant' && queryTimeMs > 0" class="response-time">
          {{ formatTime(queryTimeMs) }}
        </span>
      </div>

      <!-- 消息内容 -->
      <div class="message-bubble">
        <template v-if="role === 'assistant'">
          <!-- Markdown 渲染内容 -->
          <div
            class="markdown-body"
            v-html="renderedContent"
          ></div>
          <!-- 流式输出光标 -->
          <span v-if="isStreaming" class="streaming-cursor">▌</span>
        </template>
        <template v-else>
          <div class="user-text">{{ content }}</div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'

/**
 * Markdown 渲染器实例
 * 开启 HTML 标签支持、链接自动识别和换行转换
 */
const md = new MarkdownIt({
  html: false,  // 关闭HTML渲染，防止XSS注入
  linkify: true,
  breaks: true,
})

/**
 * Props 定义
 */
const props = defineProps({
  /** 消息角色：'user' | 'assistant' */
  role: {
    type: String,
    required: true,
    validator: (v) => ['user', 'assistant'].includes(v),
  },
  /** 消息内容 */
  content: {
    type: String,
    default: '',
  },
  /** 来源信息列表（仅助手消息） */
  sources: {
    type: Array,
    default: () => [],
  },
  /** 查询耗时（毫秒） */
  queryTimeMs: {
    type: Number,
    default: 0,
  },
  /** 是否正在流式输出 */
  isStreaming: {
    type: Boolean,
    default: false,
  },
})

/**
 * 渲染后的 Markdown 内容
 */
const renderedContent = computed(() => {
  if (!props.content) return ''
  return md.render(props.content)
})

/**
 * 格式化响应时间
 * @param {number} ms - 毫秒数
 * @returns {string} 格式化后的时间字符串
 */
function formatTime(ms) {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const minutes = Math.floor(ms / 60000)
  const seconds = ((ms % 60000) / 1000).toFixed(0)
  return `${minutes}分${seconds}秒`
}
</script>

<style scoped>
/* ==================== 消息容器 ==================== */
.chat-message {
  display: flex;
  gap: 12px;
  padding: 16px 0;
  animation: fadeInUp 0.3s ease;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 用户消息右对齐 */
.chat-message.user {
  flex-direction: row-reverse;
}

/* ==================== 消息主体 ==================== */
.message-body {
  max-width: 75%;
  min-width: 0;
}

.chat-message.user .message-body {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

/* ==================== 消息元信息 ==================== */
.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
}

.sender-name {
  color: var(--text-secondary);
  font-weight: 500;
}

.response-time {
  color: #b0b3bb;
  font-size: 11px;
}

/* ==================== 消息气泡 ==================== */
.message-bubble {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
}

/* 用户气泡：蓝色 */
.chat-message.user .message-bubble {
  background: var(--user-msg-bg);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.user-text {
  white-space: pre-wrap;
}

/* 助手气泡：白色卡片 */
.chat-message.assistant .message-bubble {
  background: #fff;
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

/* ==================== Markdown 渲染 ==================== */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin: 12px 0 6px;
  font-weight: 600;
  color: #1a1a2e;
}

.markdown-body :deep(h1) { font-size: 1.25em; }
.markdown-body :deep(h2) { font-size: 1.15em; }
.markdown-body :deep(h3) { font-size: 1.05em; }

.markdown-body :deep(p) {
  margin: 4px 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}

.markdown-body :deep(li) {
  margin: 2px 0;
}

.markdown-body :deep(code) {
  background: #f0f2f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
  color: #e74c3c;
}

.markdown-body :deep(pre) {
  background: #282c34;
  color: #abb2bf;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
}

.markdown-body :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #e4e7ed;
  padding: 6px 12px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: #f5f7fa;
  font-weight: 600;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--primary-color);
  padding: 4px 12px;
  margin: 8px 0;
  color: #666;
  background: #f8f9fb;
  border-radius: 0 6px 6px 0;
}

.markdown-body :deep(a) {
  color: var(--primary-color);
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.markdown-body :deep(strong) {
  font-weight: 600;
  color: #1a1a2e;
}

/* ==================== 流式输出光标 ==================== */
.streaming-cursor {
  display: inline-block;
  animation: blink 0.8s infinite;
  color: var(--primary-color);
  font-weight: bold;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* ==================== 来源区域 ==================== */
.sources-area {
  margin-top: 10px;
  padding: 10px 12px;
  background: #fafbfc;
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.sources-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
  font-weight: 500;
}

.sources-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
