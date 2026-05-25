# ALIGNMENT - LangChain重构工程质检RAG系统

## 原始需求
将现有自实现的工程质检RAG系统，基于LangChain框架完全重构。

## 需求边界
- 重构范围：app/目录下所有模块 + scripts/ingest.py
- 不涉及：前端代码、Docker部署配置
- API接口：允许调整，但保持核心功能（问答/流式/来源/健康检查）

## 对现有项目的理解
1. 当前架构：自实现RAG管线（向量检索+BM25+网络检索→融合→重排序→LLM生成）
2. 核心外部依赖：DashScope（LLM+Embedding）、Tavily（网络搜索）、ChromaDB（向量库）
3. 关键特性：混合检索、并行执行、智能缓存、流式输出、来源追溯、查询重写
4. 数据：9个Markdown + 3个Excel工程质检规范文档

## 关键决策
| 决策项 | 选择 | 理由 |
|--------|------|------|
| LLM接入 | ChatTongyi | langchain-community原生支持，全特性 |
| Embedding | DashScopeEmbeddings | langchain-community原生支持 |
| 向量库 | langchain-chroma | 官方集成包 |
| BM25 | BM25Retriever | langchain-community支持 |
| 网络搜索 | TavilySearchResults | langchain-community支持 |
| 混合检索 | EnsembleRetriever | LangChain内置加权融合 |
| RAG Chain | LCEL | LangChain推荐方式 |
| API兼容 | 允许调整 | 前端可同步更新 |
| 数据迁移 | 重新入库 | 确保格式兼容 |

## 疑问澄清
- Q: DashScopeEmbeddings是否支持text-embedding-v2模型？
  A: 是，通过model参数指定
- Q: LangChain ChromaDB是否兼容现有数据？
  A: 格式有差异，建议重新入库
- Q: 表格切片如何处理？
  A: 保留自定义表格检测逻辑，LangChain的TextSplitter不支持表格
