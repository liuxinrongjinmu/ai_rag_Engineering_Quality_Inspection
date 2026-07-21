/**
 * API 请求层
 * 封装所有与后端的 HTTP 通信，包括 SSE 流式查询和 RESTful API
 */
import axios from 'axios'

/* ==================== Axios 实例 ==================== */

/**
 * 创建 Axios 实例，配置基础 URL 和超时时间
 */
const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 60000, // 60秒超时，适应 LLM 生成延迟
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * 响应拦截器：统一处理错误
 */
apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.detail || error.message || '网络请求失败'
    console.error('[API Error]', message, error)
    return Promise.reject(new Error(message))
  }
)

/* ==================== SSE 流式查询 ==================== */

/**
 * SSE 流式问答请求
 * 使用 Fetch API 的 ReadableStream 实现流式读取
 *
 * @param {Object} params - 请求参数
 * @param {string} params.question - 用户问题
 * @param {boolean} params.useWebSearch - 是否启用网络检索
 * @param {number} params.topK - 返回结果数量
 * @param {Object} callbacks - 回调函数集合
 * @param {Function} callbacks.onToken - 收到回答片段时的回调
 * @param {Function} callbacks.onDone - 回答完成时的回调，传入 { sources, queryTimeMs, usedWebSearch }
 * @param {Function} callbacks.onError - 发生错误时的回调，传入 Error 对象
 * @returns {AbortController} 用于手动中断请求
 */
export function streamQuery({ question, useWebSearch = false, topK = 5 }, callbacks) {
  const abortController = new AbortController()

  const body = JSON.stringify({
    question,
    options: {
      use_web_search: useWebSearch,
      top_k: topK,
      include_source: true,
    },
  })

  fetch('/api/v1/query/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    signal: abortController.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const errorText = await response.text().catch(() => '')
        throw new Error(`HTTP ${response.status}: ${errorText}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // 解析 SSE 事件：按双换行分割事件
        const lines = buffer.split('\n')
        buffer = ''

        let currentEvent = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            const dataStr = line.slice(6)
            try {
              const data = JSON.parse(dataStr)
              if (currentEvent === 'message' && data.type === 'answer') {
                callbacks.onToken && callbacks.onToken(data.content)
              } else if (currentEvent === 'done') {
                callbacks.onDone && callbacks.onDone({
                  sources: data.sources || [],
                  queryTimeMs: data.query_time_ms || 0,
                  usedWebSearch: data.used_web_search || false,
                  cached: data.cached || false,
                })
              } else if (currentEvent === 'error') {
                callbacks.onError && callbacks.onError(new Error(data.error || '流式查询异常'))
              }
            } catch {
              // 数据格式异常，跳过
            }
            currentEvent = ''
          } else {
            // 不完整的行，放回 buffer
            buffer += line + '\n'
          }
        }
      }
    })
    .catch((error) => {
      if (error.name !== 'AbortError') {
        callbacks.onError && callbacks.onError(error)
      }
    })

  return abortController
}

/* ==================== RESTful API ==================== */

/**
 * 获取来源详情
 * @param {string} chunkId - 切片 ID
 * @returns {Promise<Object>} 来源详情数据
 */
export function getSourceDetail(chunkId) {
  return apiClient.get(`/source/${encodeURIComponent(chunkId)}`)
}

/**
 * 获取系统健康状态
 * @returns {Promise<Object>} 健康状态数据
 */
export function getHealth() {
  return apiClient.get('/health')
}

/**
 * 上传文档
 * @param {FormData} formData - 包含文件的 FormData 对象
 * @param {Function} onProgress - 上传进度回调 (0-100)
 * @returns {Promise<Object>} 上传结果
 */
export function uploadDocument(formData, onProgress) {
  return apiClient.post('/admin/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000, // 上传 + 处理需要更长时间
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        onProgress(percent)
      }
    },
  })
}

/**
 * 获取文档列表
 * @returns {Promise<Object>} 文档列表数据
 */
export function getDocuments() {
  return apiClient.get('/admin/documents')
}

/**
 * 删除文档
 * @param {string} docId - 文档 ID
 * @returns {Promise<Object>} 删除结果
 */
export function deleteDocument(docId) {
  return apiClient.delete(`/admin/documents/${encodeURIComponent(docId)}`)
}

/**
 * 重建知识库
 * @returns {Promise<Object>} 重建结果
 */
export function rebuildKnowledge() {
  return apiClient.post('/admin/knowledge/rebuild')
}

/**
 * 获取知识库统计信息
 * @returns {Promise<Object>} 统计信息
 */
export function getStats() {
  return apiClient.get('/admin/stats')
}

export default apiClient
