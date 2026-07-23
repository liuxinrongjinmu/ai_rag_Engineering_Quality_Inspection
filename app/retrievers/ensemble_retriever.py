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

        # 动态调整 BM25 召回数量，与 Chroma 保持一致；避免默认 k=4 截断相关文档
        bm25_retriever.k = top_k * 5

        if _ensemble_retriever_instance is None:
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

    手动分别调用 Chroma 和 BM25，对各自结果先做 doc_name 匹配提升，
    再做加权 RRF 融合，避免 Chroma 的 JTG 文档把塔吊等目标文档挤出前列。

    :param query: 查询文本
    :param top_k: 返回结果数
    :return: Document列表
    """
    from app.config import get_settings
    from app.retrievers.chroma_retriever import get_chroma_retriever
    from app.retrievers.bm25_retriever import get_bm25_retriever

    settings = get_settings()

    chroma_retriever = get_chroma_retriever(top_k=top_k * 5)
    bm25_retriever = get_bm25_retriever()

    if bm25_retriever is None:
        logger.warning("BM25检索器未初始化，仅使用向量检索")
        try:
            results = chroma_retriever.invoke(query)
        except Exception as e:
            logger.warning(f"Chroma检索失败: {e}，返回空结果")
            results = []
    else:
        # 动态调整 BM25 召回数量
        bm25_retriever.k = top_k * 5

        try:
            chroma_results = chroma_retriever.invoke(query)
        except Exception as e:
            logger.warning(f"Chroma检索失败: {e}")
            chroma_results = []

        try:
            bm25_results = bm25_retriever.invoke(query)
        except Exception as e:
            logger.warning(f"BM25检索失败: {e}")
            bm25_results = []

        # 按 doc_name 去重：命中查询的文档保留全部切片，
        # 未命中的文档每个只保留最靠前的一个切片，避免刷分
        chroma_results = _deduplicate_by_doc_name(chroma_results, query=query)
        bm25_results = _deduplicate_by_doc_name(bm25_results, query=query)

        # 分别对子检索器结果做 doc_name 匹配提升，防止目标文档在子列表中被淹没
        chroma_results = _boost_doc_name_matches(chroma_results, query)
        bm25_results = _boost_doc_name_matches(bm25_results, query)

        results = _weighted_rrf_fusion(
            [chroma_results, bm25_results],
            [settings.VECTOR_WEIGHT, settings.BM25_WEIGHT],
            query=query,
        )

    # 防御性过滤：跳过 page_content 为 None 的文档（ChromaDB 脏数据）
    results = [d for d in results if d.page_content and isinstance(d.page_content, str)]

    # doc_name 命中查询核心实体词时，将该文档切片排在前面，避免被海量无关文档淹没
    results = _boost_doc_name_matches(results, query)

    logger.info(f"混合检索完成: 查询='{query[:30]}...', 结果数={len(results)}")
    return results[:top_k]


def _extract_query_keywords(query: Optional[str]) -> Set[str]:
    """
    从查询中提取核心实体词（使用 jieba 分词，避免整句作为一个词）。
    """
    if not query:
        return set()

    import jieba

    stop_words = {
        "多少", "几", "什么", "怎么", "如何", "请问", "帮我", "查一下",
        "一次", "每次", "一个", "规定", "标准", "办法", "要求", "的", "了",
        "和", "是", "在", "有", "对", "为", "与", "及", "指标", "说明",
    }

    keywords = {
        t.strip() for t in jieba.cut(query)
        if len(t.strip()) >= 2 and t.strip() not in stop_words
    }
    return keywords


def _boost_doc_name_matches(documents: List[Document], query: str) -> List[Document]:
    """
    将 doc_name 包含查询核心实体词的文档切片排在前面

    :param documents: 检索结果文档列表
    :param query: 原始查询
    :return: 重排后的文档列表
    """
    if not documents or not query:
        return documents

    keywords = _extract_query_keywords(query)
    if not keywords:
        return documents

    matched = []
    others = []
    for doc in documents:
        doc_name = doc.metadata.get("doc_name", "")
        if doc_name and any(kw in doc_name for kw in keywords):
            matched.append(doc)
        else:
            others.append(doc)

    if matched:
        logger.info(f"doc_name命中查询实体词: {len(matched)}条提前, 查询='{query[:30]}...'")

    return matched + others


def _deduplicate_by_doc_name(documents: List[Document], query: Optional[str] = None) -> List[Document]:
    """
    按 doc_name 去重，只保留每个文档在列表中最靠前的一个切片。

    避免 BM25 等稀疏检索器把同一文档的多个相似切片都排进前列，
    从而在 RRF 融合时累积过高分数，淹没其他相关文档。

    对于 doc_name 命中查询实体词的文档，保留其所有切片，
    避免目标文档内的多个相关要点被合并丢失。
    """
    query_keywords = _extract_query_keywords(query)

    seen: Set[str] = set()
    result: List[Document] = []
    for doc in documents:
        name = doc.metadata.get("doc_name", "")
        if not name:
            result.append(doc)
            continue

        # 命中查询的文档保留全部切片，确保同一文档的多个要点不丢失
        if query_keywords and any(kw in name for kw in query_keywords):
            result.append(doc)
            continue

        if name not in seen:
            seen.add(name)
            result.append(doc)
    return result


def _weighted_rrf_fusion(
    doc_lists: List[List[Document]],
    weights: List[float],
    c: int = 60,
    query: Optional[str] = None,
) -> List[Document]:
    """
    加权 Reciprocal Rank Fusion：合并多个检索器的结果列表。

    在子列表中排名越靠前权重越高，合并后按 RRF 分数倒序返回，
    并把分数写入 metadata["score"] 供后续排序使用。

    额外对 doc_name 命中查询实体词的文档加权，避免目标文档被同一文档的
    大量重复切片或海量无关文档挤出前列。
    """
    from collections import defaultdict

    if len(doc_lists) != len(weights):
        logger.warning(f"RRF 融合: 结果列表数({len(doc_lists)})与权重数({len(weights)})不一致")
        return [doc for docs in doc_lists for doc in docs]

    def _doc_key(doc: Document) -> str:
        return doc.metadata.get("chunk_id", "") or str(hash(doc.page_content[:200]))

    # 提取查询实体词，用于 doc_name 匹配加权
    query_keywords = _extract_query_keywords(query)

    rrf_score: Dict[str, float] = defaultdict(float)
    for doc_list, weight in zip(doc_lists, weights):
        for rank, doc in enumerate(doc_list, start=1):
            key = _doc_key(doc)
            score = weight / (rank + c)
            # doc_name 命中查询实体词时，额外大幅加分，确保该文档的切片不被淹没
            if query_keywords:
                doc_name = doc.metadata.get("doc_name", "")
                if doc_name and any(kw in doc_name for kw in query_keywords):
                    score += 0.5 * len([kw for kw in query_keywords if kw in doc_name])
            rrf_score[key] += score

    all_docs: List[Document] = []
    seen: Set[str] = set()
    for doc_list in doc_lists:
        for doc in doc_list:
            key = _doc_key(doc)
            if key not in seen:
                seen.add(key)
                doc.metadata["score"] = rrf_score[key]
                all_docs.append(doc)

    all_docs.sort(key=lambda d: float(d.metadata.get("score", 0.0)), reverse=True)
    return all_docs


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
    多查询混合检索 + MMR 去重

    :param queries: 扩展查询列表
    :param top_k: 每个查询的召回数
    :param final_top_k: 最终返回数，默认 top_k * 2
    :return: 去重后的 Document 列表
    """
    if final_top_k is None:
        final_top_k = top_k * 2

    all_results: List[Document] = []
    seen_ids: Set[str] = set()

    valid_queries = [q.strip() for q in queries if q.strip()]
    if not valid_queries:
        return []

    # 2 个 worker 并行检索（ChromaDB WAL 模式支持有限并发读）
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(hybrid_retrieve, q, top_k=top_k * 2): q
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

    logger.info(f"多查询合并: {len(valid_queries)}个查询 -> {len(all_results)}条去重结果")

    if not all_results:
        return []

    # doc_name 命中原始查询实体词时，优先保留进候选池
    all_results = _boost_doc_name_matches(all_results, valid_queries[0])

    # MMR 候选池截断：6个查询会召回大量候选，截断到 25 条避免 O(n²)
    max_mmr_candidates = max(final_top_k * 3, 25)
    if len(all_results) > max_mmr_candidates:
        all_results.sort(key=lambda d: float(d.metadata.get("score", 0.0)), reverse=True)
        all_results = all_results[:max_mmr_candidates]

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
