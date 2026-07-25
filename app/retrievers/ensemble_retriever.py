"""
混合检索器
基于 EnsembleRetriever 的向量 + BM25 混合检索
支持多查询扩展、MMR 去重、增大召回
"""
from typing import List, Optional, TYPE_CHECKING, Union, Dict, Set
from loguru import logger
import re

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

    # 文档专属关键词路由：查询命中特定领域词时大幅提升对应文档的切片
    results = _apply_doc_route_boost(results, query)

    # doc_name 命中查询核心实体词时，将该文档切片排在前面，避免被海量无关文档淹没
    results = _boost_doc_name_matches(results, query)

    # 兜底：未经过 RRF 融合时（如仅 Chroma/BM25 单一检索器），按位置赋予默认分数，
    # 保证下游重排序器的 score-based 加权逻辑能正常工作
    for rank, doc in enumerate(results, start=1):
        if "score" not in doc.metadata or doc.metadata.get("score") is None:
            doc.metadata["score"] = 1.0 / rank

    logger.info(f"混合检索完成: 查询='{query[:30]}...', 结果数={len(results)}")
    return results[:top_k]


def _apply_doc_route_boost(documents: List[Document], query: Optional[str]) -> List[Document]:
    """
    文档专属关键词路由：当查询包含特定领域词时，大幅提升对应文档的切片分数。
    解决多文档关键词重叠导致的文档混淆问题。

    例："水泥剂量" → JTG 3441（无机结合料），而非 JTG 3420（水泥混凝土）
    """
    if not query:
        return documents

    # 领域词 → 目标文档名的关键词映射
    ROUTE_MAP = {
        # ── 土工合成材料 (JTG E50) ──
        "土工合成": "土工合成材料",
        "土工布": "土工合成材料",
        "土工格栅": "土工合成材料",
        "排水带": "土工合成材料",
        "土工膜": "土工合成材料",

        # ── 无机结合料 (JTG 3441) ──
        "无机结合料": "无机结合料",
        "稳定材料": "无机结合料",
        "EDTA": "无机结合料",
        "水泥剂量": "无机结合料",
        "石灰有效": "无机结合料",
        "劈裂强度": "无机结合料",
        "延迟时间": "无机结合料",

        # ── 质量评定 (JTG F80) ──
        "质量评定": "质量检验评定",
        "合格率": "质量检验评定",
        "关键项目": "质量检验评定",
        "一般项目": "质量检验评定",
        "分项工程": "质量检验评定",
        "单位工程": "质量检验评定",
        "机电工程": "质量检验评定",

        # ── 检测等级 (JT/T1181) ──
        "检测等级": "检测等级管理",
        "试验检测师": "检测等级管理",
        "助理试验检测师": "检测等级管理",
        "综合类": "检测等级管理",
        "专项类": "检测等级管理",
        "检测机构": "检测等级管理",
        "信用等级": "检测等级管理",
        "换证复核": "检测等级管理",
        "等级证书": "检测等级管理",
        "检测资质": "检测等级管理",
        "检测用房": "检测等级管理",
        "综合甲级": "检测等级管理",
        "综合乙级": "检测等级管理",

        # ── 岩石试验 (JTG 3431) ──
        "岩石": "岩石试验",
        "单轴抗压": "岩石试验",
        "软化系数": "岩石试验",
        "点荷载": "岩石试验",
        "抗冻性": "岩石试验",
        "岩石密度": "岩石试验",

        # ── 监理规范 (DB43) ──
        "监理规范": "监理规范",
        "总监办": "监理规范",
        "驻地办": "监理规范",
        "监理机构": "监理规范",
        "监理工程师": "监理规范",
        "监理规划": "监理规范",
        "监理细则": "监理规范",
        "隐蔽工程": "监理规范",

        # ── 塔吊 ──
        "塔吊": "塔吊",

        # ── 水泥混凝土 (JTG 3420) ──
        "水泥混凝土": "水泥及水泥混凝土",
        "水泥试验": "水泥及水泥混凝土",
        "抗氯离子": "水泥及水泥混凝土",
        "坍落度": "水泥及水泥混凝土",
        "胶砂强度": "水泥及水泥混凝土",
        "标准稠度": "水泥及水泥混凝土",
        "水泥安定性": "水泥及水泥混凝土",
        "水泥凝结": "水泥及水泥混凝土",

        # ── 土工试验 (JTG 3430) ──
        "液限": "土工试验",
        "塑限": "土工试验",
        "CBR试验": "土工试验",
        "击实": "土工试验",
        "土分类": "土工试验",
        "压缩试验": "土工试验",
        "巨粒土": "土工试验",
        "粗粒土": "土工试验",
        "细粒土": "土工试验",
        "冻胀力": "土工试验",
        "盐胀": "土工试验",
        "溶陷": "土工试验",

        # ── 常用45项（检测频率/取样） ──
        "压实度": "常用45项",
        "施工自检": "常用45项",
        "进场": "常用45项",
        "每批": "常用45项",
        "取样要求": "常用45项",
        "取样频率": "常用45项",

        # ── 检测频率 Excel ──
        "桩基检测": "检测频率",
        "锚杆": "检测频率",
        "波形梁": "检测频率",
        "路面面层": "检测频率",
        "路基填筑": "常用45项",
    }

    boosted: Set[str] = set()
    for keyword, target in ROUTE_MAP.items():
        if keyword in query:
            boosted.add(target)

    if not boosted:
        return documents

    logger.info(f"文档路由: 查询命中 {len(boosted)} 个领域 → {boosted}")

    for doc in documents:
        doc_name = doc.metadata.get("doc_name", "")
        if doc_name and any(t in doc_name for t in boosted):
            doc.metadata["score"] = float(doc.metadata.get("score", 0.0)) + 3.0

    return documents


def _extract_query_keywords(query: Optional[str]) -> Set[str]:
    """
    从查询中提取核心实体词（使用 jieba 分词，避免整句作为一个词）。
    """
    if not query:
        return set()

    import jieba

    # 添加领域复合词，避免"细集料"被切分为"细"+"集料"而丢失精确匹配
    for word in ["细集料", "粗集料", "填料", "机制砂", "石屑", "水泥混凝土", "沥青混凝土"]:
        jieba.add_word(word, freq=1000)

    stop_words = {
        "多少", "几", "什么", "怎么", "如何", "请问", "帮我", "查一下",
        "一次", "每次", "一个", "规定", "标准", "办法", "要求", "的", "了",
        "和", "是", "在", "有", "对", "为", "与", "及", "指标", "说明",
        "哪些", "有哪", "几项",
    }

    keywords = {
        t.strip() for t in jieba.cut(query)
        if len(t.strip()) >= 2 and t.strip() not in stop_words
    }
    return keywords


_OVERVIEW_QUERY_PATTERN = re.compile(
    r'有哪些|包含哪些|哪些项目|种类|分类|类型|分为|分为几|有几[种个类]|分别是什么|都[有些]什么|关键参数|检测方法|试验项目|项目清单'
)


def _is_overview_query(query: Optional[str]) -> bool:
    """判断是否为概览/清单类查询"""
    if not query:
        return False
    return bool(_OVERVIEW_QUERY_PATTERN.search(query))


def _is_malformed_table_row(doc: Document) -> bool:
    """识别表格切片中因多行单元格错位产生的垃圾行"""
    if doc.metadata.get("chunk_type") != "table_row":
        return False
    content = doc.page_content
    # "必要时做" 占位行没有实质信息
    if "试验类别: 必要时做" in content or "类别: 必要时做" in content:
        return True
    # 序号列应当是数字，若被内容占用则为错位行
    if re.search(r'序号[:：]\s*\D', content):
        return True
    return False


def _retrieve_overview_chunks(query: str, top_k: int = 5) -> List[Document]:
    """
    显式召回 chunk_type=overview 的概览切片。
    用于"有哪些""关键参数"等 overview 查询，避免完整清单被单行表格淹没。
    """
    try:
        from app.infrastructure.vectorstore import get_vectorstore

        vectorstore = get_vectorstore()
        docs = vectorstore.similarity_search(
            query,
            k=max(top_k * 3, 10),
            filter={"chunk_type": "overview"},
        )
    except Exception as e:
        logger.warning(f"Overview 检索失败: {e}")
        return []

    query_keywords = _extract_query_keywords(query)
    filtered: List[Document] = []
    for doc in docs:
        # 无明确实体词时不过滤；有实体词时要求内容命中
        if query_keywords and not any(kw in doc.page_content for kw in query_keywords):
            continue
        # 给予较高初始分，确保进入候选池前列
        doc.metadata["score"] = float(doc.metadata.get("score", 0.0)) + 3.0
        filtered.append(doc)

    if filtered:
        logger.info(f"Overview 检索命中: {len(filtered)}条, 查询='{query[:30]}...'")
    return filtered


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
    按 doc_name 去重，默认只保留每个文档在列表中最靠前的一个切片。

    避免 BM25 等稀疏检索器把同一文档的多个相似切片都排进前列，
    从而在 RRF 融合时累积过高分数，淹没其他相关文档。

    例外：
    - doc_name 命中查询实体词的文档，保留其所有切片，避免目标文档内的多个相关要点被合并丢失。
    - 概览/目录切片（chunk_type=overview 或 is_overview）始终保留，确保"有哪些"等 overview 查询能命中完整列表。
    """
    query_keywords = _extract_query_keywords(query)

    seen: Set[str] = set()
    # 记录每个文档已保留的切片数，避免内容相关切片被过度去重
    doc_keep_counts: Dict[str, int] = {}
    max_keep_per_doc = 3

    result: List[Document] = []
    for doc in documents:
        name = doc.metadata.get("doc_name", "")
        chunk_type = doc.metadata.get("chunk_type", "")
        is_overview = doc.metadata.get("is_overview") or chunk_type == "overview"

        if not name:
            result.append(doc)
            continue

        # 概览切片始终保留
        if is_overview:
            result.append(doc)
            continue

        # doc_name 命中查询的文档保留全部切片
        if query_keywords and any(kw in name for kw in query_keywords):
            result.append(doc)
            continue

        # 内容命中查询核心实体词的文档，保留前 N 个相关切片，避免同一文档内关键信息丢失
        content_hits = sum(1 for kw in query_keywords if kw in doc.page_content) if query_keywords else 0
        if content_hits > 0:
            current_count = doc_keep_counts.get(name, 0)
            if current_count < max_keep_per_doc:
                doc_keep_counts[name] = current_count + 1
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

                # 内容命中查询核心实体词时额外加分（帮助 doc_name 不含关键词但内容相关的文档）
                content = doc.page_content
                matched_content_keywords = [kw for kw in query_keywords if kw in content]
                if matched_content_keywords:
                    score += 0.15 * len(matched_content_keywords)

            # 概览/目录切片在概览类问题中优先进入候选池
            if doc.metadata.get("chunk_type") == "overview" or doc.metadata.get("is_overview"):
                score += 3.0

            # 项目/参数清单类表格行额外加分
            if doc.metadata.get("chunk_type") == "table_row":
                content = doc.page_content
                if any(kw in content for kw in ["试验项目", "检测项目", "参数", "指标"]):
                    score += 0.15

            # 过滤因多行单元格错位产生的垃圾表格行
            if _is_malformed_table_row(doc):
                score -= 2.0

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

    # ChromaDB SQLite 后端对并发读支持有限，多线程会导致 'Could not connect to tenant' 等错误，
    # 因此改为串行执行，保证每次查询都稳定召回。
    for q in valid_queries:
        try:
            results = hybrid_retrieve(q, top_k=top_k * 2)
            for doc in results:
                chunk_id = doc.metadata.get("chunk_id", "")
                content_hash = hash(doc.page_content) % 10000000
                key = chunk_id if chunk_id else f"content_{content_hash}"
                if key not in seen_ids:
                    seen_ids.add(key)
                    all_results.append(doc)
        except Exception as e:
            logger.warning(f"扩展查询检索失败: {q[:30]}... - {e}")

    logger.info(f"多查询合并: {len(valid_queries)}个查询 -> {len(all_results)}条去重结果")

    # 概览类查询额外召回 overview 切片，确保完整清单不被单行表格淹没
    original_query = valid_queries[0]
    if _is_overview_query(original_query):
        overview_chunks = _retrieve_overview_chunks(original_query, top_k=final_top_k)
        for doc in overview_chunks:
            chunk_id = doc.metadata.get("chunk_id", "")
            content_hash = hash(doc.page_content) % 10000000
            key = chunk_id if chunk_id else f"content_{content_hash}"
            if key not in seen_ids:
                seen_ids.add(key)
                all_results.insert(0, doc)
        logger.info(f"概览查询补充 overview 切片后: {len(all_results)}条")

    if not all_results:
        return []

    # doc_name 命中原始查询实体词时，优先保留进候选池
    all_results = _boost_doc_name_matches(all_results, original_query)

    # MMR 候选池截断：6个查询会召回大量候选，截断到 50 条避免 O(n²) 并保留更多潜在相关文档
    max_mmr_candidates = max(final_top_k * 5, 50)
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

        # 优先选择概览/目录切片，确保"有哪些"等 overview 查询不被 MMR 多样性惩罚过滤
        overview_indices = [
            i for i in remaining
            if documents[i].metadata.get("chunk_type") == "overview"
            or documents[i].metadata.get("is_overview")
        ]
        for idx in overview_indices:
            if len(selected) < top_k:
                selected.append(idx)
                remaining.remove(idx)

        # 如果还有空位，先选最相关的非 overview 文档
        if remaining and len(selected) < top_k:
            first_idx = int(np.argmax(query_similarities[remaining]))
            actual_first_idx = remaining[first_idx]
            selected.append(actual_first_idx)
            remaining.remove(actual_first_idx)

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
