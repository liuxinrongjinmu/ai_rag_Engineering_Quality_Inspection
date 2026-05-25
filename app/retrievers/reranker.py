"""
重排序器
对检索结果进行重排序，本地优先
"""
from typing import List, Optional
from loguru import logger

from langchain_core.documents import Document


class Reranker:
    """
    检索结果重排序器
    本地结果优先策略
    """

    def __init__(
        self,
        local_weight: float = 0.7,
        web_weight: float = 0.3,
    ):
        """
        初始化重排序器

        :param local_weight: 本地结果权重
        :param web_weight: 网络结果权重
        """
        self.local_weight = local_weight
        self.web_weight = web_weight

    def rerank(
        self,
        local_results: List[Document],
        web_results: List[Document],
        top_k: int = 5,
    ) -> List[Document]:
        """
        重排序并合并结果

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

        logger.info(f"重排序完成: 本地{len(local_results)}条, 网络{len(web_results)}条, 最终{len(final_results)}条")
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
        _reranker_instance = Reranker(local_weight, web_weight)

    return _reranker_instance
