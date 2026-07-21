<!--
  聊天输入组件
  支持文本输入、网络检索开关和发送按钮
-->
<template>
  <div class="chat-input-wrapper">
    <!-- 网络检索开关 -->
    <div class="input-options">
      <el-switch
        v-model="useWebSearch"
        size="small"
        active-text="网络检索已开启"
        inactive-text="仅本地知识库"
        class="web-switch"
      />
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <el-input
        ref="inputRef"
        v-model="inputText"
        type="textarea"
        :rows="3"
        :disabled="disabled"
        :placeholder="disabled ? '正在生成回答...' : '请输入您的问题，Enter 发送，Shift+Enter 换行'"
        resize="none"
        class="input-textarea"
        @keydown="handleKeydown"
      />
      <el-button
        type="primary"
        :disabled="!canSend"
        :loading="disabled"
        class="send-btn"
        @click="handleSend"
      >
        <el-icon v-if="!disabled"><Promotion /></el-icon>
        <span>{{ disabled ? '发送中' : '发送' }}</span>
      </el-button>
    </div>

    <!-- 底部提示 -->
    <div class="input-hint">
      <span>内容由AI生成，仅供参考</span>
      <span>{{ inputText.length }}/1000</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

/**
 * Props 定义
 */
const props = defineProps({
  /** 是否禁用（加载状态） */
  disabled: {
    type: Boolean,
    default: false,
  },
})

/**
 * Emits 定义
 */
const emit = defineEmits(['send'])

/**
 * 输入框引用
 */
const inputRef = ref(null)

/**
 * 输入文本
 */
const inputText = ref('')

/**
 * 是否启用网络检索
 */
const useWebSearch = ref(false)

/**
 * 防抖定时器
 */
let debounceTimer = null

/**
 * 是否可以发送：文本非空且未禁用
 */
const canSend = computed(() => {
  return inputText.value.trim().length > 0 && !props.disabled
})

/**
 * 处理键盘事件
 * Enter 发送，Shift+Enter 换行
 */
function handleKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (canSend.value) {
      handleSend()
    }
  }
}

/**
 * 发送消息（带300ms防抖，防止快速重复点击）
 */
function handleSend() {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }

  debounceTimer = setTimeout(() => {
    const text = inputText.value.trim()
    if (!text) return

    emit('send', {
      question: text,
      useWebSearch: useWebSearch.value,
    })

    // 清空输入
    inputText.value = ''

    // 重新聚焦输入框
    setTimeout(() => {
      inputRef.value?.focus()
    }, 50)

    debounceTimer = null
  }, 300)
}
</script>

<style scoped>
/* ==================== 容器 ==================== */
.chat-input-wrapper {
  background: #fff;
  border-top: 1px solid var(--border-color);
  padding: 12px 16px 8px;
}

/* ==================== 选项栏 ==================== */
.input-options {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.web-switch {
  --el-switch-on-color: #e6a23c;
  font-size: 12px;
}

/* ==================== 输入区域 ==================== */
.input-area {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.input-textarea {
  flex: 1;
}

.input-textarea :deep(.el-textarea__inner) {
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.5;
  background: #f8f9fb;
  transition: background 0.2s, border-color 0.2s;
}

.input-textarea :deep(.el-textarea__inner:focus) {
  background: #fff;
}

.input-textarea :deep(.el-textarea__inner:disabled) {
  background: #f0f2f5;
  cursor: not-allowed;
}

.send-btn {
  flex-shrink: 0;
  border-radius: 10px;
  padding: 10px 20px;
  font-size: 14px;
}

.send-btn .el-icon {
  margin-right: 4px;
}

/* ==================== 底部提示 ==================== */
.input-hint {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 11px;
  color: #c0c4cc;
  padding: 0 4px;
}
</style>
