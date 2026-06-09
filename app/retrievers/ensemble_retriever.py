"""
混合检索器
基于EnsembleRetriever的向量+BM25混合检索
"""
from typing import List, Optional
from loguru import logger

from langchain_core.documents import Document


_ensemble_retriever_instance: Optional[object] = None


def get_ensemble_retriever(
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
    top_k: int = 5,
) -> object:
    """
    获取EnsembleRetriever单例

    :param vector_weight: 向量检索权重
    :param bm25_weight: BM25检索权重
    :param top_k: 返回结果数
    :return: EnsembleRetriever实例
    """
    global _ensemble_retriever_instance

    if _ensemble_retriever_instance is None:
        from langchain.retrievers import EnsembleRetriever
        from app.retrievers.chroma_retriever import get_chroma_retriever
        from app.retrievers.bm25_retriever import get_bm25_retriever

        chroma_retriever = get_chroma_retriever(top_k=top_k * 2)
        bm25_retriever = get_bm25_retriever()

        if bm25_retriever is None:
            logger.warning("BM25检索器未初始化，仅使用向量检索")
            return chroma_retriever

        _ensemble_retriever_instance = EnsembleRetriever(
            retrievers=[chroma_retriever, bm25_retriever],
            weights=[vector_weight, bm25_weight],
        )
        logger.info(f"EnsembleRetriever初始化成功: weights=[{vector_weight}, {bm25_weight}]")

    return _ensemble_retriever_instance


def hybrid_retrieve(query: str, top_k: int = 5) -> List[Document]:
    """
    执行混合检索

    :param query: 查询文本
    :param top_k: 返回结果数
    :return: Document列表
    """
    from app.config import get_settings

    settings = get_settings()
    retriever = get_ensemble_retriever(
        vector_weight=settings.VECTOR_WEIGHT,
        bm25_weight=settings.BM25_WEIGHT,
        top_k=top_k,
    )

    try:
        results = retriever.invoke(query)
        logger.info(f"混合检索完成: 查询='{query[:30]}...', 结果数={len(results)}")
        return results[:top_k]
    except Exception as e:
        logger.error(f"混合检索失败: {e}")
        return []
