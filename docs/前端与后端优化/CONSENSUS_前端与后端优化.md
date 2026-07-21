# CONSENSUS - 前端界面与后端优化

## 一、需求描述

在现有工程质检RAG系统（v2.1.0）基础上，完成以下扩展：

1. **前端用户界面**：基于 Vue 3 + Element Plus 构建问答交互界面，支持SSE流式对话
2. **管理员界面**：提供文档上传、知识库管理和系统状态查看功能
3. **后端改进**：单元测试覆盖、检索并行化、Redis缓存、类型注解完善

## 二、验收标准

### 2.1 前端验收

| 场景 | 预期结果 |
|------|---------|
| 用户输入问题并发送 | SSE流式展示答案，显示来源卡片，展示响应时间 |
| 点击「查看原文」 | 弹窗显示完整原文、前后文上下文，支持复制 |
| 切换「网络检索」开关 | 影响查询时是否触发Tavily搜索 |
| 发送空问题 | 发送按钮禁用，无法提交 |
| 后端不可达 | 显示友好错误提示"服务连接失败，请稍后重试" |
| 桌面/平板/移动端 | 响应式布局自适应 |
| 管理页面上传MD/XLS文件 | 文件上传成功，自动触发入库 |
| 管理页面查看文档列表 | 显示已入库文档名、切片数、上传时间 |
| 管理页面删除文档 | 从ChromaDB和BM25索引中移除 |
| 管理页面查看系统状态 | 显示ChromaDB/LLM/Embedding状态和统计 |

### 2.2 后端验收

| 指标 | 目标 |
|------|------|
| 单元测试覆盖率 | 核心模块 > 70% |
| 检索并行化效果 | 网络检索与本地检索并行，延迟降低20-30% |
| Redis缓存 | 配置REDIS_URL后启用Redis；不配置降级内存 |
| 类型注解 | 所有工厂函数返回具体类型，0个 `-> object` |

### 2.3 性能验收

| 指标 | 目标值 |
|------|--------|
| 前端首屏加载 | < 2秒 |
| 缓存命中响应 | < 100ms（Redis/内存） |
| 并行检索延迟 | < 原串行延迟的70% |

## 三、技术实现方案

### 3.1 前端技术栈

| 组件 | 技术选择 |
|------|---------|
| 框架 | Vue 3 (Composition API + `<script setup>`) |
| 构建 | Vite 5 |
| UI库 | Element Plus |
| 路由 | Vue Router 4 |
| HTTP | Axios（管理API）/ Fetch API（SSE流式） |
| 样式 | CSS变量 + Element Plus主题 |

### 3.2 前端项目结构

```
frontend/
├── public/
├── src/
│   ├── views/
│   │   ├── ChatView.vue        # 问答交互页面
│   │   └── AdminView.vue       # 管理员页面
│   ├── components/
│   │   ├── ChatMessage.vue     # 单条消息气泡
│   │   ├── SourceCard.vue      # 来源卡片
│   │   ├── SourceDetail.vue    # 来源详情弹窗
│   │   ├── ChatInput.vue       # 输入区域
│   │   ├── QuickQuestions.vue  # 快捷问题推荐
│   │   ├── DocList.vue         # 文档列表
│   │   ├── DocUpload.vue       # 文档上传
│   │   └── SystemStatus.vue    # 系统状态面板
│   ├── api/
│   │   └── index.js            # API封装（Fetch SSE + Axios）
│   ├── router/
│   │   └── index.js            # 路由配置
│   ├── App.vue                 # 根组件
│   └── main.js                 # 入口
├── index.html
├── vite.config.js
└── package.json
```

### 3.3 后端新增/修改

```
工程质检RAG系统/
├── app/
│   ├── api/routes/
│   │   └── admin.py            # [新增] 管理API
│   ├── utils/
│   │   └── cache.py            # [修改] 添加Redis后端 + 内存降级
│   ├── core/
│   │   └── orchestrator.py     # [修改] 检索并行化 + 类型注解
│   ├── infrastructure/         # [修改] 类型注解
│   ├── retrievers/             # [修改] 类型注解
│   ├── config.py               # [修改] 添加REDIS_URL配置
├── tests/                      # [新增] 测试目录
│   ├── __init__.py
│   ├── test_chunker.py
│   ├── test_query_rewriter.py
│   ├── test_reranker.py
│   ├── test_cache.py
│   └── test_document_loaders.py
├── requirements.txt            # [修改] 添加redis, pytest等
└── docker-compose.yml          # [修改] 可选Redis服务
```

### 3.4 新增API接口

| 方法 | 路径 | 功能 |
|------|------|------|
| `POST` | `/api/v1/admin/documents/upload` | 上传文档（MD/XLS/XLSX） |
| `GET` | `/api/v1/admin/documents` | 获取已入库文档列表 |
| `DELETE` | `/api/v1/admin/documents/{doc_id}` | 删除指定文档及切片 |
| `POST` | `/api/v1/admin/knowledge/rebuild` | 全量重建知识库 |
| `GET` | `/api/v1/admin/stats` | 获取知识库统计详情 |

### 3.5 架构图

```mermaid
graph TB
    subgraph 前端
        CHAT[问答界面<br/>ChatView.vue]
        ADMIN[管理界面<br/>AdminView.vue]
        ROUTER[Vue Router]
    end

    subgraph API层
        QUERY[/api/v1/query<br/>query.py]
        STREAM[/api/v1/query/stream]
        SOURCE[/api/v1/source]
        HEALTH[/api/v1/health]
        UPLOAD[/api/v1/admin/*<br/>admin.py 新增]
    end

    subgraph 后端改进
        ORCH[Orchestrator<br/>检索并行化]
        CACHE[QueryCache<br/>Redis + 内存降级]
        REDIS[(Redis<br/>可选)]
    end

    CHAT -->|SSE流式| STREAM
    CHAT -->|HTTP| SOURCE
    ADMIN -->|HTTP| UPLOAD
    ADMIN -->|HTTP| HEALTH
    STREAM --> ORCH
    ORCH --> CACHE
    CACHE --> REDIS
```

## 四、任务边界限制

### 4.1 包含
- Vue 3 问答界面（SSE流式、来源追溯、响应式布局）
- Vue 3 管理界面（文档上传/删除、知识库重建、系统状态）
- 后端文档管理API（上传/列表/删除/重建）
- pytest单元测试（5个核心模块）
- Orchestrator检索并行化
- Redis缓存（可选降级）
- 全部 `-> object` 改为具体类型

### 4.2 不包含
- 用户认证/权限系统
- 多轮对话/会话管理
- E2E测试/压力测试
- PDF自动转换（仍需用户手动转MD）
- 前端i18n国际化
