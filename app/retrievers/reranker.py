"""
重排序器
对检索结果进行重排序，支持DashScope语义重排序和本地优先策略
"""
from typing import List, Optional
from loguru import logger

from langchain_core.documents import Document


class Reranker:
    """
    检索结果重排序器
    优先使用DashScope语义重排序模型，不可用时回退到本地优先策略
    """

    def __init__(
        self,
        local_weight: float = 0.7,
        web_weight: float = 0.3,
        api_key: Optional[str] = None,
        use_semantic_rerank: bool = True,
    ):
        """
        初始化重排序器

        :param local_weight: 本地结果权重（回退策略使用）
        :param web_weight: 网络结果权重（回退策略使用）
        :param api_key: DashScope API Key（语义重排序使用）
        :param use_semantic_rerank: 是否启用语义重排序
        """
        self.local_weight = local_weight
        self.web_weight = web_weight
        self.api_key = api_key
        self.use_semantic_rerank = use_semantic_rerank

    def rerank(
        self,
        local_results: List[Document],
        web_results: List[Document],
        top_k: int = 5,
        query: Optional[str] = None,
    ) -> List[Document]:
        """
        重排序并合并结果

        :param local_results: 本地检索结果
        :param web_results: 网络检索结果
        :param top_k: 返回数量
        :param query: 原始查询（语义重排序需要）
        :return: 重排序后的结果
        """
        all_results = local_results + web_results

        if not all_results:
            return []

        # 尝试语义重排序
        if self.use_semantic_rerank and query and self.api_key:
            try:
                return self._semantic_rerank(all_results, query, top_k)
            except Exception as e:
                logger.warning(f"语义重排序失败，回退到本地优先策略: {e}")

        # 回退到本地优先策略
        return self._fallback_rerank(local_results, web_results, top_k)

    def _semantic_rerank(
        self,
        documents: List[Document],
        query: str,
        top_k: int,
    ) -> List[Document]:
        """
        使用DashScope重排序模型进行语义重排序

        :param documents: 所有待排序文档
        :param query: 查询文本
        :param top_k: 返回数量
        :return: 重排序后的结果
        """
        import dashscope
        from dashscope import TextReRank

        dashscope.api_key = self.api_key

        documents_text = [doc.page_content for doc in documents]

        response = TextReRank.call(
            model="gte-rerank",
            query=query,
            documents=documents_text,
            top_n=top_k,
            return_documents=False,
        )

        if response.status_code != 200:
            logger.warning(f"DashScope重排序API返回错误: {response.code} - {response.message}")
            raise RuntimeError(f"DashScope重排序失败: {response.message}")

        reranked_results = []
        for item in response.output.results:
            idx = item.index
            score = item.relevance_score
            doc = documents[idx]
            doc.metadata["rerank_score"] = score
            reranked_results.append(doc)

        logger.info(f"语义重排序完成: 输入{len(documents)}条, 输出{len(reranked_results)}条")
        return reranked_results[:top_k]

    def _fallback_rerank(
        self,
        local_results: List[Document],
        web_results: List[Document],
        top_k: int,
    ) -> List[Document]:
        """
        本地优先策略重排序（回退方案）

        :param local_results: 本地检索结果
        :param web_results: 网络检索结果
        :param top_k: 返回数量
        :return: 重排序后的结果
        """
        scored_results = []

        for i, doc in enumerate(local_results):
            score = self.local_weight * (1.0 - i * 0.05)
            scored_results.append((score, doc))

        for i, doc in enumerate(web_results):
            score = self.web_weight * (1.0 - i * 0.05)
            scored_results.append((score, doc))

        scored_results.sort(key=lambda x: x[0], reverse=True)
        final_results = [doc for _, doc in scored_results[:top_k]]

        logger.info(f"重排序完成(本地优先): 本地{len(local_results)}条, 网络{len(web_results)}条, 最终{len(final_results)}条")
        return final_results


_reranker_instance: Optional[Reranker] = None


def get_reranker(
    local_weight: float = 0.7,
    web_weight: float = 0.3,
) -> Reranker:
    """
    获取Reranker单例

    :param local_weight: 本地结果权重
    :param web_weight: 网络结果权重
    :return: Reranker实例
    """
    global _reranker_instance

    if _reranker_instance is None:
        from app.config import get_settings
        settings = get_settings()

        _reranker_instance = Reranker(
            local_weight=local_weight,
            web_weight=web_weight,
            api_key=settings.DASHSCOPE_API_KEY,
            use_semantic_rerank=True,
        )

    return _reranker_instance
