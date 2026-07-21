"""
重排序器（Reranker）单元测试
测试本地优先回退策略、空输入处理、Top-K 限制等功能
"""
import sys
import os

# 将项目根目录加入 sys.path，确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from langchain_core.documents import Document

from app.retrievers.reranker import Reranker


class TestRerankerFallback:
    """Reranker._fallback_rerank 单元测试 —— 不依赖外部 API"""

    def test_fallback_rerank_local_priority(self):
        """
        测试：回退策略下本地结果应获得更高权重，排在前面
        """
        reranker = Reranker(
            local_weight=0.7,
            web_weight=0.3,
            use_semantic_rerank=False,  # 禁用语义重排序，走回退
        )

        local_docs = [
            Document(page_content="本地文档：路基压实度检测方法", metadata={"source": "local", "score": 0.9}),
            Document(page_content="本地文档：沥青混合料检测规范", metadata={"source": "local", "score": 0.8}),
        ]

        web_docs = [
            Document(page_content="网络搜索结果：压实度相关文章", metadata={"source": "web", "score": 0.7}),
            Document(page_content="网络搜索结果：检测标准解读", metadata={"source": "web", "score": 0.6}),
        ]

        results = reranker.rerank(
            local_results=local_docs,
            web_results=web_docs,
            top_k=4,
        )

        # 验证返回结果非空
        assert len(results) > 0, "应返回非空结果"

        # 本地文档应排在前列（至少第一个本地文档在第一个网络文档之前）
        local_positions = []
        web_positions = []
        for i, doc in enumerate(results):
            source = doc.metadata.get("source", "")
            if source == "local":
                local_positions.append(i)
            elif source == "web":
                web_positions.append(i)

        # 至少有一个本地文档排在最前面
        if local_positions and web_positions:
            assert min(local_positions) < min(web_positions), \
                "本地文档应排在网络文档之前"

    def test_fallback_rerank_empty_input(self):
        """
        测试：空列表输入应返回空列表
        """
        reranker = Reranker(
            local_weight=0.7,
            web_weight=0.3,
            use_semantic_rerank=False,
        )

        # 两个空列表
        results1 = reranker.rerank(local_results=[], web_results=[], top_k=5)
        assert results1 == [], "两个空列表应返回空列表"

        # 仅本地有结果
        local_only = [Document(page_content="测试文档", metadata={"source": "local"})]
        results2 = reranker.rerank(local_results=local_only, web_results=[], top_k=5)
        assert len(results2) == 1, "仅本地有一个结果时应返回该结果"

        # 仅网络有结果
        web_only = [Document(page_content="网络文档", metadata={"source": "web"})]
        results3 = reranker.rerank(local_results=[], web_results=web_only, top_k=5)
        assert len(results3) == 1, "仅网络有一个结果时应返回该结果"

    def test_fallback_rerank_top_k_limit(self):
        """
        测试：返回结果数量受 top_k 参数限制
        """
        reranker = Reranker(
            local_weight=0.7,
            web_weight=0.3,
            use_semantic_rerank=False,
        )

        # 构造 10 个本地文档 + 10 个网络文档
        local_docs = [
            Document(page_content=f"本地文档 #{i}", metadata={"source": "local", "index": i})
            for i in range(10)
        ]
        web_docs = [
            Document(page_content=f"网络文档 #{i}", metadata={"source": "web", "index": i})
            for i in range(10)
        ]

        # top_k = 3，应仅返回 3 条
        results = reranker.rerank(
            local_results=local_docs,
            web_results=web_docs,
            top_k=3,
        )
        assert len(results) == 3, f"top_k=3 时应返回 3 条，实际返回 {len(results)}"

        # top_k = 5
        results5 = reranker.rerank(
            local_results=local_docs,
            web_results=web_docs,
            top_k=5,
        )
        assert len(results5) == 5, f"top_k=5 时应返回 5 条，实际返回 {len(results5)}"

        # top_k 大于总结果数，应返回所有结果
        results_over = reranker.rerank(
            local_results=local_docs,
            web_results=web_docs,
            top_k=50,
        )
        assert len(results_over) == 20, \
            f"top_k=50 但只有 20 个文档，应返回全部 20 条，实际返回 {len(results_over)}"

    def test_fallback_rerank_scoring_order(self):
        """
        测试：回退策略按权重排序的正确性
        高权重文档应在低权重文档之前
        """
        reranker = Reranker(
            local_weight=0.7,
            web_weight=0.3,
            use_semantic_rerank=False,
        )

        # 构造不同权重的文档，验证排序
        local_docs = [
            Document(page_content="Local-1", metadata={"source": "local", "idx": 1}),
            Document(page_content="Local-2", metadata={"source": "local", "idx": 2}),
        ]
        web_docs = [
            Document(page_content="Web-1", metadata={"source": "web", "idx": 1}),
        ]

        results = reranker.rerank(
            local_results=local_docs,
            web_results=web_docs,
            top_k=3,
        )

        # 第一个结果应该是本地文档（权重最高）
        assert results[0].metadata.get("source") == "local", \
            "第一个结果应为本地文档（权重最高）"

        # 结果应包含所有 3 个文档
        assert len(results) == 3, "应返回全部 3 个文档"

        sources = [doc.metadata.get("source") for doc in results]
        assert sources.count("local") == 2, "应有 2 个本地文档"
        assert sources.count("web") == 1, "应有 1 个网络文档"

    def test_fallback_rerank_document_integrity(self):
        """
        测试：重排序不修改原始 Document 内容
        """
        reranker = Reranker(
            local_weight=0.7,
            web_weight=0.3,
            use_semantic_rerank=False,
        )

        original_content = "路基压实度检测应按每层每200m检测不少于4个点，采用灌砂法或环刀法。"
        original_metadata = {"source": "local", "page": 1, "standard": "JTG 3450-2019"}

        local_docs = [
            Document(page_content=original_content, metadata=original_metadata.copy()),
        ]

        results = reranker.rerank(local_results=local_docs, web_results=[], top_k=5)

        assert len(results) == 1, "应返回 1 个文档"
        assert results[0].page_content == original_content, "文档内容应保持不变"
        assert results[0].metadata.get("standard") == "JTG 3450-2019", \
            "元数据中的 standard 应保留"
        assert results[0].metadata.get("page") == 1, "元数据中的 page 应保留"
