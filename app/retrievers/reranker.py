"""
重排序器
对检索结果进行重排序，支持DashScope语义重排序和本地优先策略
"""
from typing import List, Optional, Dict
from loguru import logger
import re

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
        重排序并合并结果，语义重排 + 本地Boost 融合评分

        :param local_results: 本地检索结果
        :param web_results: 网络检索结果
        :param top_k: 返回数量
        :param query: 原始查询（语义重排序需要）
        :return: 重排序后的结果
        """
        all_results = local_results + web_results

        if not all_results:
            return []

        # 表格片段加权：表格行通常包含精确答案
        boosted_results = self._boost_table_rows(all_results, query)

        # 尝试语义重排序 + Boost 融合评分
        if self.use_semantic_rerank and query and self.api_key:
            try:
                return self._semantic_boost_fusion(boosted_results, query, top_k)
            except Exception as e:
                logger.warning(f"语义重排序失败，回退到本地优先策略: {e}")

        # 回退到本地优先策略
        return self._fallback_rerank(local_results, web_results, top_k)

    def _semantic_boost_fusion(
        self,
        documents: List[Document],
        query: str,
        top_k: int,
    ) -> List[Document]:
        """
        语义重排序 + Boost 分数融合：
        gte-rerank语义分 * 0.5 + 本地Boost分(normalized) * 0.5

        避免语义重排过滤掉领域特有的Boost加权片段
        """
        import dashscope
        from dashscope import TextReRank
        dashscope.api_key = self.api_key

        documents_text = [doc.page_content[:1500] for doc in documents]

        response = TextReRank.call(
            model="gte-rerank",
            query=query,
            documents=documents_text,
            top_n=min(len(documents), max(top_k * 3, 10)),
            return_documents=False,
        )

        if response.status_code != 200:
            logger.warning(f"DashScope重排序API返回错误: {response.code} - {response.message}")
            raise RuntimeError(f"DashScope重排序失败: {response.message}")

        # gte-rerank 返回的 relevance_score (0~1)
        semantic_scores: Dict[int, float] = {}
        for item in response.output.results:
            semantic_scores[item.index] = item.relevance_score

        # 提取本地 Boost 分数并归一化
        boost_scores_raw = [float(d.metadata.get("score", 0.0)) for d in documents]
        max_boost = max(boost_scores_raw) if boost_scores_raw else 1.0
        min_boost = min(boost_scores_raw) if boost_scores_raw else 0.0
        boost_range = max_boost - min_boost or 1.0

        # 融合评分: 语义分(0.5) + Boost归一化分(0.5)
        fused = []
        for i, doc in enumerate(documents):
            sem_score = semantic_scores.get(i, 0.0)
            boost_norm = (boost_scores_raw[i] - min_boost) / boost_range
            fused_score = 0.5 * sem_score + 0.5 * boost_norm
            fused.append((fused_score, doc))

        fused.sort(key=lambda x: x[0], reverse=True)
        result = [doc for _, doc in fused[:top_k]]

        logger.info(f"语义+Boost融合重排序完成: 输入{len(documents)}条, 输出{len(result)}条")
        return result

    def _boost_table_rows(
        self,
        documents: List[Document],
        query: Optional[str],
    ) -> List[Document]:
        """
        对表格行片段进行加权：如果查询包含"扣分/罚款/多少"等数值类词语，
        提升包含明确数值的表格行优先级
        """
        if not query:
            return documents

        value_keywords = re.findall(r'扣[几分]?|罚[款]?|多少|金额|标准|分值|扣分|几|不低于|不超过|是多少|多大', query)
        has_value_query = bool(value_keywords)

        # 数值型查询（问尺寸/规格/频率/距离等）额外检测
        has_numeric_query = bool(re.search(
            r'多少|几[个处次](?![类种项个])|直径|粒径|尺寸|规格|频率|间距|厚度|温度|不低于|不超过|不小于|不大于|大于|小于|等于',
            query
        ))

        # 提取查询中的核心实体词（长度>=2），用于内容匹配加权
        query_entity_keywords = self._extract_entity_keywords(query)

        boosted = []
        for doc in documents:
            score_boost = 0.0
            content = doc.page_content
            metadata = doc.metadata
            chunk_type = metadata.get("chunk_type")

            # 表格行 / 条例项通常包含精确答案，优先提升
            if chunk_type == "table_row" or chunk_type == "article" or metadata.get("is_table"):
                score_boost += 0.05

            # HTML表格片段（含结构化数据如 ≥96, 4.75mm），大幅加权
            is_html_table = bool(re.search(r'<t[dhr]', content))
            if is_html_table:
                # 含查询实体词时权重更高
                entity_hit = any(kw in content for kw in query_entity_keywords) if query_entity_keywords else False
                score_boost += 0.12 if entity_hit else 0.06
                # ≥ ≤ 等比较符号 + 数字 = 高价值结构化数据
                if re.search(r'[≥≤><]\s*\d+', content):
                    score_boost += 0.04

            # 数值型查询：大幅提升包含"数值+单位"的片段
            if has_numeric_query:
                # 匹配常见技术单位格式：50mm, 4.75mm, 96%, 105℃, 60T, 20m, 5个等
                if re.search(r'\d+\.?\d*\s*(mm|cm|m|km|℃|T|t|kg|g|%|个|处|次|点|分钟|小时|年)', content):
                    score_boost += 0.10
                # 匹配数值范围：2.0~2.5, 105~110 等
                if re.search(r'\d+\.?\d*\s*[~～-]\s*\d+', content):
                    score_boost += 0.04
                # 匹配精确小数：2.36mm, 4.75mm 类高精度技术数值
                if re.search(r'\d+\.\d{2,}', content):
                    score_boost += 0.03

            if has_value_query:
                # 包含数字/分值的加分
                if re.search(r'\d+\s*[分元]?', content):
                    score_boost += 0.03

                # 包含"扣分"、"分值"等关键词的加分
                if any(kw in content for kw in ['扣分', '分值', '罚款', '金额']):
                    score_boost += 0.02

            # 内容包含查询核心实体词额外加权，帮助区分相似条例
            if query_entity_keywords:
                matched_keywords = [kw for kw in query_entity_keywords if kw in content]
                if matched_keywords:
                    score_boost += 0.08 * len(matched_keywords)

            # 强信号词匹配（如"投诉"对应投诉条款），额外大幅加权
            strong_signals = self._extract_strong_signals(query)
            if strong_signals:
                matched_signals = [s for s in strong_signals if s in content]
                score_boost += 0.15 * len(matched_signals)

            # 小文档加权：切片数较少的文档（<300切片）在索引中覆盖不足，
            # 当查询命中时将对应切片略微提升，避免被大文档淹没
            doc_chunk_count = metadata.get("doc_total_chunks", 0)
            if 0 < doc_chunk_count < 100:
                score_boost += 0.06  # 极小文档（如<100切片）额外加权
            elif 0 < doc_chunk_count < 300:
                score_boost += 0.03

            if score_boost > 0 and "score" in metadata:
                metadata["score"] = float(metadata.get("score", 0.0)) + score_boost

            boosted.append(doc)

        # 按加权后的分数排序（如果存在）
        try:
            boosted.sort(
                key=lambda d: float(d.metadata.get("score", 0.0)),
                reverse=True
            )
        except Exception:
            pass

        return boosted

    def _extract_entity_keywords(self, query: str) -> List[str]:
        """
        从查询中提取核心实体词，用于内容匹配加权
        """
        # 过滤停用词和通用词，保留具体名词
        stop_words = {
            '的', '了', '和', '是', '在', '有', '对', '为', '与', '及', '或',
            '多少', '几', '什么', '怎么', '如何', '请问', '帮我', '查一下',
            '一次', '每次', '一个', '一次', '规定', '标准', '办法',
        }
        # 提取长度>=2 的中文词、字母数字词
        tokens = re.findall(r'[\u4e00-\u9fa5]{2,}|[A-Za-z0-9]+', query)
        keywords = [t for t in tokens if t not in stop_words and len(t) >= 2]
        return keywords

    def _extract_strong_signals(self, query: str) -> List[str]:
        """
        提取查询中的强信号词，这些词在内容中匹配时应大幅提升权重
        """
        signals = []
        signal_patterns = {
            '投诉': ['投诉', '客户投诉', '被投诉'],
            '罚款': ['罚款', '罚金'],
            '逾期': ['逾期'],
            '不良资产': ['不良资产'],
            '廉洁': ['廉洁', '不廉洁'],
        }
        for _, variants in signal_patterns.items():
            for variant in variants:
                if variant in query:
                    signals.extend(variants)
                    break
        return list(set(signals))

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
            use_semantic_rerank=settings.USE_SEMANTIC_RERANK,
        )

    return _reranker_instance
