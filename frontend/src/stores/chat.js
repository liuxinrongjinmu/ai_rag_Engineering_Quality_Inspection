/**
 * 对话状态共享模块（Vue 3 响应式单例）
 * 消息列表在路由切换时保持，不会被销毁
 */
import { reactive } from 'vue'

/**
 * 对话消息结构
 * @typedef {Object} ChatMessage
 * @property {'user'|'assistant'} role
 * @property {string} content
 * @property {Array} sources
 * @property {number} queryTimeMs
 * @property {boolean} isStreaming
 */

const state = reactive({
  /** @type {ChatMessage[]} 消息列表 */
  messages: [],
  /** 是否正在等待 AI 回复 */
  isLoading: false,
  /** 当前 SSE AbortController */
  currentAbortController: null,
})

export function useChatStore() {
  return {
    state,

    /** 添加消息 */
    addMessage(msg) {
      state.messages.push(msg)
    },

    /** 更新最后一条消息 */
    updateLastMessage(updates) {
      const last = state.messages[state.messages.length - 1]
      if (last) {
        Object.assign(last, updates)
      }
    },

    /** 获取最后一条助手消息的索引 */
    getLastAssistantIndex() {
      return state.messages.length - 1
    },

    /** 清空对话历史 */
    newChat() {
      if (state.currentAbortController) {
        state.currentAbortController.abort()
        state.currentAbortController = null
      }
      state.messages.length = 0
      state.isLoading = false
    },

    /** 设置加载状态 */
    setLoading(val) {
      state.isLoading = val
    },

    /** 设置 AbortController */
    setAbortController(ctrl) {
      state.currentAbortController = ctrl
    },

    /** 中断当前请求 */
    abortCurrentRequest() {
      if (state.currentAbortController) {
        state.currentAbortController.abort()
        state.currentAbortController = null
        // 将最后一条流式消息标记为完成
        const last = state.messages[state.messages.length - 1]
        if (last && last.role === 'assistant' && last.isStreaming) {
          last.isStreaming = false
          if (!last.content) {
            last.content = '回答已中断。'
          }
        }
        state.isLoading = false
      }
    },
  }
}
