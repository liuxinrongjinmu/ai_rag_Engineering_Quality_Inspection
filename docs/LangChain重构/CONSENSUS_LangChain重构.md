# CONSENSUS - LangChain重构工程质检RAG系统

## 需求描述
将工程质检RAG系统从自实现架构迁移到LangChain框架，保持核心功能不变，利用LangChain生态简化代码、提升可维护性。

## 验收标准
1. 所有API接口功能正常（问答/流式/来源/健康检查）
2. 混合检索（向量+BM25+网络）正常工作
3. 流式输出正常工作
4. 来源追溯正常工作
5. 智能缓存正常工作
6. 数据入库流程正常
7. 代码基于LangChain框架，无自实现的检索/生成逻辑

## 技术方案
- LLM: ChatTongyi (langchain-community)
- Embedding: DashScopeEmbeddings (langchain-community)
- VectorStore: Chroma (langchain-chroma)
- BM25: BM25Retriever (langchain-community)
- Web: TavilySearchResults (langchain-community)
- 混合检索: EnsembleRetriever (langchain)
- RAG Chain: LCEL (langchain-core)
- 文本切片: 保留自定义chunker（表格支持）+ LangChain Document格式
- 缓存: 保留现有QueryCache
- 日志: 保留现有loguru

## 技术约束
- Python 3.10+
- LangChain >= 0.3.x
- 保持.env配置方式
- API KEY放.env文件

## 集成方案
- FastAPI + LangChain LCEL
- SSE流式输出通过LangChain streaming + FastAPI StreamingResponse
- 缓存层在Chain外部包装
