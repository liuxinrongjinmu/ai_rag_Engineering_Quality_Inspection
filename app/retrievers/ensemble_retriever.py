"""
混合检索器
基于 EnsembleRetriever 的向量 + BM25 混合检索
支持多查询扩展、MMR 去重、增大召回
"""
from typing import List, Optional, TYPE_CHECKING, Union, Dict, Set
from loguru import logger

from langchain_core.documents import Document

if TYPE_CHECKING:
    from langchain.retrievers import EnsembleRetriever
    from langchain_core.retrievers import BaseRetriever

_ensemble_retriever_instance: Optional["EnsembleRetriever"] = None
_cached_weights: Optional[tuple] = None  # (vector_weight, bm25_weight)


def get_ensemble_retriever(
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
    top_k: int = 5,
) -> Union["EnsembleRetriever", "BaseRetriever"]:
    """
    获取EnsembleRetriever单例

    :param vector_weight: 向量检索权重
    :param bm25_weight: BM25检索权重
    :param top_k: 返回结果数
    :return: EnsembleRetriever实例
    """
    global _ensemble_retriever_instance, _cached_weights

    current_weights = (vector_weight, bm25_weight)

    # 权重变化时重建实例
    if _ensemble_retriever_instance is not None and _cached_weights != current_weights:
        _ensemble_retriever_instance = None
        logger.info(f"权重变化，重建EnsembleRetriever: {_cached_weights} -> {current_weights}")

    if _ensemble_retriever_instance is None:
        from langchain.retrievers import EnsembleRetriever
        from app.retrievers.chroma_retriever import get_chroma_retriever
        from app.retrievers.bm25_retriever import get_bm25_retriever

        chroma_retriever = get_chroma_retriever(top_k=top_k * 5)
        bm25_retriever = get_bm25_retriever()

        if bm25_retriever is None:
            logger.warning("BM25检索器未初始化，仅使用向量检索")
            return chroma_retriever

        _ensemble_retriever_instance = EnsembleRetriever(
            retrievers=[chroma_retriever, bm25_retriever],
            weights=[vector_weight, bm25_weight],
        )
        _cached_weights = current_weights
        logger.info(f"EnsembleRetriever初始化成功: weights=[{vector_weight}, {bm25_weight}]")

    return _ensemble_retriever_instance


def hybrid_retrieve(query: str, top_k: int = 5) -> List[Document]:
    """
    执行混合检索（单查询）

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
    except Exception as e:
        logger.warning(f"EnsembleRetriever调用失败: {e}，回退到单检索器")
        results = _fallback_single_retrieve(query, top_k)

    # 防御性过滤：跳过 page_content 为 None 的文档（ChromaDB 脏数据）
    results = [d for d in results if d.page_content and isinstance(d.page_content, str)]
    logger.info(f"混合检索完成: 查询='{query[:30]}...', 结果数={len(results)}")
    return results[:top_k]


def _fallback_single_retrieve(query: str, top_k: int = 5) -> List[Document]:
    """
    EnsembleRetriever 异常时的回退检索：先试 BM25，再试 Chroma
    """
    results = []
    from app.retrievers.bm25_retriever import get_bm25_retriever
    bm25 = get_bm25_retriever()
    if bm25:
        try:
            results = bm25.invoke(query)
            if results:
                return results[:top_k * 2]
        except Exception:
            pass
    from app.retrievers.chroma_retriever import get_chroma_retriever
    chroma = get_chroma_retriever(top_k=top_k * 2)
    try:
        results = chroma.invoke(query)
    except Exception:
        pass
    return results[:top_k * 2] if results else []


def multi_query_hybrid_retrieve(
    queries: List[str],
    top_k: int = 5,
    final_top_k: Optional[int] = None,
) -> List[Document]:
    """
    多查询混合检索 + MMR 去重（并行执行所有查询，大幅降低延迟）

    :param queries: 扩展查询列表
    :param top_k: 每个查询的召回数
    :param final_top_k: 最终返回数，默认 top_k * 2
    :return: 去重后的 Document 列表
    """
    if final_top_k is None:
        final_top_k = top_k * 2

    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_results: List[Document] = []
    seen_ids: Set[str] = set()

    # 并行执行所有查询的混合检索
    valid_queries = [q.strip() for q in queries if q.strip()]
    if not valid_queries:
        return []

    with ThreadPoolExecutor(max_workers=min(len(valid_queries), 6)) as executor:
        futures = {
            executor.submit(hybrid_retrieve, q, top_k=top_k * 3): q
            for q in valid_queries
        }
        for future in as_completed(futures):
            try:
                results = future.result()
                for doc in results:
                    chunk_id = doc.metadata.get("chunk_id", "")
                    content_hash = hash(doc.page_content) % 10000000
                    key = chunk_id if chunk_id else f"content_{content_hash}"
                    if key not in seen_ids:
                        seen_ids.add(key)
                        all_results.append(doc)
            except Exception as e:
                logger.warning(f"并行检索子任务失败: {futures[future][:30]}... - {e}")

    logger.info(f"并行多查询合并: {len(valid_queries)}个查询 -> {len(all_results)}条去重结果")

    if not all_results:
        return []

    # MMR 去重：先限制候选池大小避免 O(n²) 瓶颈
    if len(all_results) > final_top_k * 3:
        all_results.sort(key=lambda d: float(d.metadata.get("score", 0.0)), reverse=True)
        all_results = all_results[:final_top_k * 3]

    return _mmr_deduplicate(all_results, valid_queries[0], final_top_k)


def _mmr_deduplicate(
    documents: List[Document],
    query: str,
    top_k: int,
    lambda_param: float = 0.7,
) -> List[Document]:
    """
    MMR去重：平衡相关性与多样性（候选池已在上层截断，性能可控）

    :param documents: 候选文档
    :param query: 原始查询
    :param top_k: 返回数量
    :param lambda_param: 相关性权重(0.7=优先相关,兼顾多样)
    :return: MMR 排序后的文档
    """
    if len(documents) <= top_k:
        return documents

    try:
        from app.infrastructure.embeddings import get_embeddings
        import numpy as np

        embeddings = get_embeddings()
        query_embedding = np.array(embeddings.embed_query(query))
        doc_embeddings = np.array(embeddings.embed_documents([d.page_content for d in documents]))

        # 归一化向量，cosine → dot product，避免重复归一化
        query_embedding = query_embedding / (np.linalg.norm(query_embedding) + 1e-10)
        doc_embeddings = doc_embeddings / (np.linalg.norm(doc_embeddings, axis=1, keepdims=True) + 1e-10)

        # cosine similarity = dot product of normalized vectors
        query_similarities = np.dot(doc_embeddings, query_embedding)

        selected: List[int] = []
        remaining: List[int] = list(range(len(documents)))

        # 先选最相关的
        first_idx = int(np.argmax(query_similarities))
        selected.append(first_idx)
        remaining.remove(first_idx)

        # MMR: lambda * relevance - (1-lambda) * max_similarity_to_selected
        while remaining and len(selected) < top_k:
            relevance = query_similarities[remaining]
            # 与已选文档的相似度矩阵: len(remaining) × len(selected)
            sim_matrix = np.dot(doc_embeddings[remaining], doc_embeddings[selected].T)
            max_sim = np.max(sim_matrix, axis=1) if selected else np.zeros(len(remaining))
            scores = lambda_param * relevance - (1 - lambda_param) * max_sim
            best_local_idx = int(np.argmax(scores))
            selected.append(remaining[best_local_idx])
            remaining.pop(best_local_idx)

        logger.info(f"MMR去重: {len(documents)}条 -> {len(selected)}条")
        return [documents[i] for i in selected]

    except Exception as e:
        # 回退：按分数排序取 top_k
        logger.warning(f"MMR去重失败，回退到简化排序: {e}")
        sorted_docs = sorted(
            documents,
            key=lambda d: float(d.metadata.get("score", 0.0)),
            reverse=True
        )
        seen = set()
        result = []
        for doc in sorted_docs:
            h = hash(doc.page_content[:200])
            if h not in seen:
                seen.add(h)
                result.append(doc)
                if len(result) >= top_k:
                    break
        return result
