# TODO - LangChain重构待办事项

## 需要配置的环境变量

在 `.env` 文件中填入真实的API Key：

```
DASHSCOPE_API_KEY=your_dashscope_api_key_here  # 必须替换为真实Key
TAVILY_API_KEY=your_tavily_api_key_here         # 必须替换为真实Key（网络检索功能需要）
```

获取方式：
- DashScope API Key: https://dashscope.console.aliyun.com/apiKey
- Tavily API Key: https://tavily.com/#api

## 可选优化项

1. **LangSmith追踪**：配置LANGCHAIN_API_KEY启用LangSmith追踪，可视化调试RAG Chain
2. **Redis缓存**：将QueryCache从内存缓存升级为Redis，支持多实例部署
3. **异步检索**：将检索和LLM调用改为异步(async)，提升并发性能
4. **重排序模型**：接入DashScope重排序模型替代当前简单的权重融合
5. **Agent模式**：利用LangChain Agent实现多轮对话和工具调用
6. **前端适配**：API接口有微调，前端需要同步更新（主要在SSE流式格式）

## 注意事项

- 当前LangChain版本为1.3.0，EnsembleRetriever在langchain_classic包中
- DashScope Embedding API限制单条文本不超过2048字符，chunker已做安全截断
- BM25索引文件(bm25_index.pkl)需要与ChromaDB数据同步更新
