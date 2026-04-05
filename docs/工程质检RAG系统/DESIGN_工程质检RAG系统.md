# DESIGN - 工程质检RAG系统

## 一、整体架构图

```mermaid
graph TB
    subgraph 用户层
        U[用户/客户端]
    end
    
    subgraph API层
        API[FastAPI服务]
        AUTH[请求验证]
    end
    
    subgraph 核心服务层
        ORCH[查询编排器]
        RAG[RAG引擎]
        HYBRID[混合检索器]
    end
    
    subgraph 检索层
        LOCAL[本地检索器]
        WEB[网络检索器]
        RERANK[重排序器]
    end
    
    subgraph 数据层
        VDB[(向量数据库<br/>ChromaDB)]
        META[(元数据存储<br/>SQLite)]
        CACHE[(缓存层)]
    end
    
    subgraph 数据处理层
        PARSER[文档解析器]
        CHUNKER[切片器]
        EMBED[向量化]
        INGEST[入库管道]
    end
    
    subgraph 外部服务
        LLM[LLM服务<br/>GPT-4o/DeepSeek]
        EMBED_API[Embedding API]
        SEARCH_API[搜索API<br/>Tavily/Serper]
    end
    
    subgraph 原始数据
        PDF[PDF文档]
        XLS[Excel文件]
    end
    
    U --> API
    API --> AUTH
    AUTH --> ORCH
    ORCH --> RAG
    RAG --> HYBRID
    HYBRID --> LOCAL
    HYBRID --> WEB
    LOCAL --> VDB
    LOCAL --> META
    WEB --> SEARCH_API
    LOCAL --> RERANK
    WEB --> RERANK
    RERANK --> RAG
    RAG --> LLM
    LLM --> API
    
    PDF --> PARSER
    XLS --> PARSER
    PARSER --> CHUNKER
    CHUNKER --> EMBED
    EMBED --> INGEST
    INGEST --> VDB
    INGEST --> META
    
    EMBED --> EMBED_API
```

## 二、分层设计

### 2.1 目录结构

```
工程质检RAG系统/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI入口
│   ├── config.py               # 配置管理
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── query.py        # 问答接口
│   │   │   ├── health.py       # 健康检查
│   │   │   └── source.py       # 来源追溯
│   │   └── deps.py             # 依赖注入
│   ├── core/
│   │   ├── __init__.py
│   │   ├── orchestrator.py     # 查询编排器
│   │   ├── rag_engine.py       # RAG引擎
│   │   └── hybrid_retriever.py # 混合检索器
│   ├── retrievers/
│   │   ├── __init__.py
│   │   ├── local_retriever.py  # 本地检索
│   │   ├── web_retriever.py    # 网络检索
│   │   └── reranker.py         # 重排序
│   ├── processors/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py       # PDF解析
│   │   ├── excel_parser.py     # Excel解析
│   │   ├── chunker.py          # 切片器
│   │   └── embedder.py         # 向量化
│   ├── models/
│   │   ├── __init__.py
│   │   ├── document.py         # 文档模型
│   │   ├── chunk.py            # 切片模型
│   │   └── response.py         # 响应模型
│   └── utils/
│       ├── __init__.py
│       ├── logger.py           # 日志
│       └── helpers.py          # 工具函数
├── data/
│   ├── raw/                    # 原始数据
│   ├── processed/              # 处理后数据
│   └── vectordb/               # 向量数据库
├── scripts/
│   ├── ingest.py               # 数据入库脚本
│   └── test_scenarios.py       # 测试场景
├── tests/
│   ├── test_retrieval.py
│   └── test_api.py
├── docs/
│   └── 工程质检RAG系统/
├── .env.example
├── requirements.txt
└── README.md
```

### 2.2 核心组件说明

| 组件 | 职责 | 关键技术 |
|------|------|---------|
| FastAPI服务 | HTTP接口暴露、请求处理 | FastAPI, Pydantic |
| 查询编排器 | 协调检索、生成流程 | 状态机模式 |
| RAG引擎 | 检索增强生成核心逻辑 | LangChain/LlamaIndex |
| 混合检索器 | 本地+网络检索协调 | 策略模式 |
| 本地检索器 | 向量相似度检索 | ChromaDB, cosine similarity |
| 网络检索器 | 外部搜索API调用 | Tavily/Serper API |
| 重排序器 | 结果排序优化 | Cross-encoder |
| 文档解析器 | PDF/Excel解析 | PyMuPDF, pandas |
| 切片器 | 文本分块 | 递归字符切分 |
| 向量化 | 文本转向量 | OpenAI/BGE Embedding |

## 三、模块依赖关系图

```mermaid
graph LR
    subgraph API模块
        A1[query.py]
        A2[health.py]
        A3[source.py]
    end
    
    subgraph 核心模块
        C1[orchestrator.py]
        C2[rag_engine.py]
        C3[hybrid_retriever.py]
    end
    
    subgraph 检索模块
        R1[local_retriever.py]
        R2[web_retriever.py]
        R3[reranker.py]
    end
    
    subgraph 处理模块
        P1[pdf_parser.py]
        P2[excel_parser.py]
        P3[chunker.py]
        P4[embedder.py]
    end
    
    subgraph 数据模型
        M1[document.py]
        M2[chunk.py]
        M3[response.py]
    end
    
    A1 --> C1
    A3 --> R1
    
    C1 --> C2
    C2 --> C3
    C3 --> R1
    C3 --> R2
    R1 --> R3
    R2 --> R3
    
    P1 --> P3
    P2 --> P3
    P3 --> P4
    
    R1 --> M2
    P3 --> M2
    P1 --> M1
```

## 四、接口契约定义

### 4.1 问答接口

**POST /api/v1/query**

请求：
```json
{
    "question": "土方路基压实度检测频率是多少？",
    "options": {
        "use_web_search": true,
        "top_k": 5,
        "include_source": true
    }
}
```

响应：
```json
{
    "code": 0,
    "data": {
        "answer": "根据JTG F80-1-2017《公路工程质量检验评定标准》...",
        "sources": [
            {
                "doc_id": "JTG_F80-1-2017",
                "doc_name": "公路工程质量检验评定标准 第一册 土建工程",
                "page": 15,
                "section": "4.2.2",
                "content": "土方路基压实度检测频率...",
                "source_type": "local"
            }
        ],
        "confidence": 0.92,
        "query_time_ms": 1234
    }
}
```

### 4.2 来源追溯接口

**GET /api/v1/source/{chunk_id}**

响应：
```json
{
    "code": 0,
    "data": {
        "chunk_id": "chunk_001",
        "doc_id": "JTG_F80-1-2017",
        "doc_name": "公路工程质量检验评定标准",
        "page": 15,
        "section": "4.2.2 土方路基",
        "full_content": "...完整段落内容...",
        "context_before": "...前文...",
        "context_after": "...后文..."
    }
}
```

### 4.3 健康检查接口

**GET /api/v1/health**

响应：
```json
{
    "status": "healthy",
    "components": {
        "vectordb": "ok",
        "llm": "ok",
        "embedder": "ok"
    },
    "stats": {
        "total_chunks": 15000,
        "total_docs": 14
    }
}
```

## 五、数据流向图

### 5.1 数据入库流程

```mermaid
flowchart LR
    subgraph 输入
        PDF[PDF文件]
        XLS[Excel文件]
    end
    
    subgraph 解析
        P1[PDF解析器]
        P2[Excel解析器]
    end
    
    subgraph 处理
        C1[文本清洗]
        C2[切片器]
        C3[元数据提取]
    end
    
    subgraph 向量化
        E1[Embedding API]
    end
    
    subgraph 存储
        VDB[(向量数据库)]
        META[(元数据DB)]
    end
    
    PDF --> P1
    XLS --> P2
    P1 --> C1
    P2 --> C1
    C1 --> C2
    C2 --> C3
    C3 --> E1
    E1 --> VDB
    C3 --> META
```

### 5.2 查询处理流程

```mermaid
flowchart TD
    Q[用户问题] --> P1[问题预处理]
    P1 --> P2[问题向量化]
    P2 --> L1{本地检索}
    
    L1 -->|有结果| R1[结果排序]
    L1 -->|无结果| W1[网络检索]
    
    W1 --> W2[来源过滤]
    W2 --> R1
    
    R1 --> C1[上下文构建]
    C1 --> LLM[LLM生成]
    LLM --> A1[答案后处理]
    A1 --> A2[添加来源追溯]
    A2 --> R[返回结果]
```

## 六、异常处理策略

### 6.1 异常分类

| 异常类型 | 处理策略 | 用户提示 |
|---------|---------|---------|
| PDF解析失败 | 记录日志，跳过该文件 | 入库报告中标注 |
| Embedding API超时 | 重试3次，降级到备用模型 | 响应时间延长 |
| LLM调用失败 | 返回检索结果，标注生成失败 | "检索到相关内容，但无法生成总结" |
| 网络检索失败 | 仅返回本地结果 | "网络检索暂时不可用" |
| 向量库查询失败 | 降级到关键词检索 | "使用备用检索方式" |

### 6.2 降级策略

```python
class DegradationStrategy:
    def get_retriever(self):
        if self.vectordb_available:
            return VectorRetriever()
        elif self.keyword_index_available:
            return KeywordRetriever()
        else:
            return WebOnlyRetriever()
    
    def get_embedder(self):
        if self.primary_embedder_available:
            return PrimaryEmbedder()
        else:
            return FallbackEmbedder()
```

## 七、性能指标

| 指标 | 目标值 | 测量方法 |
|------|--------|---------|
| 单次问答延迟 | <3秒 | API响应时间 |
| 检索准确率 | ≥80% | 测试集评估 |
| 向量化吞吐 | >100 chunks/s | 批量处理测试 |
| 并发支持 | 10 QPS | 压力测试 |

---

**文档版本**：v1.0  
**创建时间**：2026-04-05  
**状态**：待确认
