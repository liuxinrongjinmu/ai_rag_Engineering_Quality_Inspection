"""
查询编排器
协调整个问答流程：缓存→检索→重排序→RAG Chain→来源提取
支持异步并行本地+网络检索
"""
import asyncio
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Generator, Tuple
from loguru import logger
import time

from langchain_core.documents import Document

from app.config import get_settings
from app.chains.rag_chain import invoke_rag, stream_rag
from app.retrievers.ensemble_retriever import hybrid_retrieve, multi_query_hybrid_retrieve
from app.retrievers.web_retriever import search_web
from app.retrievers.reranker import get_reranker
from app.processors.query_rewriter import get_query_rewriter
from app.utils.cache import get_query_cache
from app.models.response import QueryData, SourceInfo
from app.models.document import SourceType


def _format_num(val: float) -> str:
    """
    格式化数值：整数不带小数，小数保留原有精度

    :param val: 数值
    :return: 格式化后的字符串
    """
    if val == int(val):
        return str(int(val))
    return f"{val}".rstrip('0').rstrip('.') if '.' in str(val) else str(int(val))


class QueryOrchestrator:
    """
    查询编排器
    协调检索、重排序、生成流程
    """

    def __init__(self):
        """
        初始化查询编排器
        """
        self.settings = get_settings()
        self._ensure_bm25_loaded()

    async def process_query(
        self,
        question: str,
        use_web_search: bool = False,
        top_k: int = 5,
        use_cache: bool = True,
    ) -> QueryData:
        """
        异步处理查询（带缓存优化，并行本地+网络检索）

        :param question: 用户问题
        :param use_web_search: 是否使用网络检索
        :param top_k: 返回结果数
        :param use_cache: 是否使用缓存
        :return: 查询结果
        """
        start_time = time.time()

        logger.info(f"处理查询: {question[:50]}...")

        if use_cache:
            cache = get_query_cache()
            cached_result = cache.get(question, use_web_search)
            if cached_result:
                cached_result['query_time_ms'] = int((time.time() - start_time) * 1000)
                logger.info("缓存命中，返回缓存结果")
                return QueryData(**cached_result)

        # 1. 查询重写与扩展
        query_rewriter = get_query_rewriter(api_key=self.settings.DASHSCOPE_API_KEY)
        rewritten_query = query_rewriter.rewrite(question)
        expanded_queries = query_rewriter.expand_query(rewritten_query)
        if rewritten_query != question:
            logger.info(f"查询已重写: {rewritten_query}")
        if len(expanded_queries) > 1:
            logger.info(f"查询已扩展为 {len(expanded_queries)} 个: {expanded_queries}")

        # 2. 并行：本地多查询混合检索 + 网络检索
        web_results: List[Document] = []
        used_web_search = False

        if use_web_search:
            # 先快速判断是否需要网络检索（不阻塞主流程）
            local_preview = await asyncio.to_thread(
                multi_query_hybrid_retrieve, expanded_queries, top_k=top_k, final_top_k=top_k * 5
            )
            if self._should_search_web(local_preview):
                local_task = asyncio.to_thread(
                    multi_query_hybrid_retrieve, expanded_queries, top_k=top_k, final_top_k=top_k * 5
                )
                web_task = asyncio.to_thread(search_web, question, top_k)
                try:
                    local_results, web_results = await asyncio.gather(
                        local_task, web_task
                    )
                except Exception as e:
                    logger.warning(f"并行检索异常: {e}")
                    local_results = local_preview
                    web_results = []
                used_web_search = len(web_results) > 0
            else:
                local_results = local_preview
        else:
            local_results = await asyncio.to_thread(
                multi_query_hybrid_retrieve, expanded_queries, top_k=top_k, final_top_k=top_k * 5
            )

        logger.info(
            "[DEBUG] 多查询检索后 top10: "
            + ", ".join([f"{d.metadata.get('doc_name', '?')[:20]}" for d in local_results[:10]])
        )

        # 3. 重排序（输入窗口更大）
        reranker = get_reranker(
            local_weight=self.settings.LOCAL_WEIGHT,
            web_weight=self.settings.WEB_WEIGHT,
        )
        final_results = reranker.rerank(
            local_results=local_results,
            web_results=web_results,
            top_k=top_k,
            query=question,
        )

        logger.info(
            f"[DEBUG] 重排序后 top{top_k}: "
            + ", ".join([f"{d.metadata.get('doc_name', '?')[:20]}" for d in final_results[:top_k]])
        )

        if not final_results:
            query_time = int((time.time() - start_time) * 1000)
            return QueryData(
                answer="抱歉，没有找到相关的信息来回答您的问题。请尝试换一种方式提问。",
                sources=[],
                query_time_ms=query_time,
                used_web_search=False,
            )

        # 4. RAG生成
        answer = invoke_rag(question, final_results)

        # 4.5. 数值反向校验：修正LLM幻觉数值
        answer = self._verify_numeric_values(answer, final_results)

        # 5. 提取来源
        sources = self._extract_sources(final_results)

        query_time = int((time.time() - start_time) * 1000)
        logger.info(f"查询完成: 耗时{query_time}ms")

        result_data = QueryData(
            answer=answer,
            sources=sources,
            query_time_ms=query_time,
            used_web_search=used_web_search,
        )

        if use_cache:
            cache = get_query_cache()
            cache.set(
                question=question,
                data=result_data.model_dump(),
                use_web_search=use_web_search,
            )

        return result_data

    async def process_query_stream(
        self,
        question: str,
        use_web_search: bool = False,
        top_k: int = 5,
    ) -> Tuple[Generator[str, None, None], List[SourceInfo], bool]:
        """
        异步流式处理查询（并行本地+网络检索）

        :param question: 用户问题
        :param use_web_search: 是否使用网络检索
        :param top_k: 返回结果数
        :return: (文本片段生成器, 来源信息列表, 是否使用网络检索)
        """
        logger.info(f"流式处理查询: {question[:50]}...")

        # 1. 查询重写与扩展
        query_rewriter = get_query_rewriter(api_key=self.settings.DASHSCOPE_API_KEY)
        rewritten_query = query_rewriter.rewrite(question)
        expanded_queries = query_rewriter.expand_query(rewritten_query)

        # 2. 并行：本地多查询混合检索 + 网络检索
        web_results: List[Document] = []
        used_web_search = False

        if use_web_search:
            local_preview = await asyncio.to_thread(
                multi_query_hybrid_retrieve, expanded_queries, top_k=top_k, final_top_k=top_k * 5
            )
            if self._should_search_web(local_preview):
                local_task = asyncio.to_thread(
                    multi_query_hybrid_retrieve, expanded_queries, top_k=top_k, final_top_k=top_k * 5
                )
                web_task = asyncio.to_thread(search_web, question, top_k)
                try:
                    local_results, web_results = await asyncio.gather(
                        local_task, web_task
                    )
                except Exception as e:
                    logger.warning(f"并行检索异常: {e}")
                    local_results = local_preview
                    web_results = []
                used_web_search = len(web_results) > 0
            else:
                local_results = local_preview
        else:
            local_results = await asyncio.to_thread(
                multi_query_hybrid_retrieve, expanded_queries, top_k=top_k, final_top_k=top_k * 5
            )

        # 3. 重排序
        reranker = get_reranker(
            local_weight=self.settings.LOCAL_WEIGHT,
            web_weight=self.settings.WEB_WEIGHT,
        )
        final_results = reranker.rerank(
            local_results=local_results,
            web_results=web_results,
            top_k=top_k,
            query=question,
        )

        if not final_results:
            sources = []
            def empty_gen():
                yield "抱歉，没有找到相关的信息来回答您的问题。"
            return empty_gen(), sources, False

        # 4. 提取来源（在流式生成前提取）
        sources = self._extract_sources(final_results)

        # 5. 流式生成（缓冲完整答案→数值校验→一次性输出）
        final_results_copy = final_results  # 闭包引用

        def stream_generator():
            buffer = []
            for chunk in stream_rag(question, final_results_copy):
                buffer.append(chunk)
            # LLM生成完毕后进行数值校验
            full_answer = ''.join(buffer)
            verified = self._verify_numeric_values(full_answer, final_results_copy)
            yield verified

        return stream_generator(), sources, used_web_search

    def get_source_detail(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        获取来源详情

        :param chunk_id: 切片ID
        :return: 来源详情
        """
        try:
            from app.infrastructure.vectorstore import get_vectorstore

            vectorstore = get_vectorstore()
            collection = vectorstore._collection

            results = collection.get(
                where={"chunk_id": chunk_id},
                include=["documents", "metadatas"],
                limit=1,
            )

            if not results or not results.get("ids"):
                return None

            metadata = results["metadatas"][0] if results.get("metadatas") else {}
            content = results["documents"][0] if results.get("documents") else ""

            # 查询上下文：同一文档中相邻切片
            context_before = self._get_adjacent_chunk(
                collection, metadata, direction="before"
            )
            context_after = self._get_adjacent_chunk(
                collection, metadata, direction="after"
            )

            return {
                "chunk_id": chunk_id,
                "doc_id": metadata.get("doc_id", ""),
                "doc_name": metadata.get("doc_name", ""),
                "page": metadata.get("page"),
                "section": metadata.get("section"),
                "full_content": content,
                "context_before": context_before,
                "context_after": context_after,
            }

        except Exception as e:
            logger.error(f"获取来源详情失败: {e}")
            return None

    def _get_adjacent_chunk(
        self,
        collection,
        metadata: Dict[str, Any],
        direction: str,
    ) -> Optional[str]:
        """
        获取相邻切片内容

        :param collection: ChromaDB集合
        :param metadata: 当前切片的元数据
        :param direction: 方向，"before"或"after"
        :return: 相邻切片内容，不存在则返回None
        """
        doc_id = metadata.get("doc_id", "")
        chunk_index = metadata.get("chunk_index")

        if not doc_id or chunk_index is None:
            return None

        try:
            offset = -1 if direction == "before" else 1
            target_index = chunk_index + offset

            results = collection.get(
                where={
                    "$and": [
                        {"doc_id": {"$eq": doc_id}},
                        {"chunk_index": {"$eq": target_index}},
                    ]
                },
                include=["documents"],
                limit=1,
            )

            if results and results.get("documents"):
                return results["documents"][0]
        except Exception as e:
            logger.debug(f"获取相邻切片失败: {e}")

        return None

    def _ensure_bm25_loaded(self):
        """
        确保 BM25 索引已加载
        """
        try:
            from app.retrievers.bm25_retriever import load_bm25_retriever, get_bm25_retriever

            if get_bm25_retriever() is None:
                bm25_path = Path(self.settings.BM25_INDEX_PATH)
                if bm25_path.exists():
                    load_bm25_retriever(str(bm25_path))
        except Exception as e:
            logger.warning(f"BM25索引加载失败: {e}")

    def _verify_numeric_values(
        self,
        answer: str,
        retrieved_docs: List[Document],
    ) -> str:
        """
        生成后的数值反向校验层

        从生成的答案中提取所有"数值+单位"表达式，与检索到的上下文中
        的数值进行比对。如果答案中的数值在上下文中不存在但上下文中有
        相近数值（±50%范围），则将答案数值替换为上下文中的数值。

        典型修复案例：
        - LLM输出"95%" → 上下文中有"96%" → 修正为"96%"
        - LLM输出"10%" → 上下文中有"20%" → 修正为"20%"
        - LLM输出"1小时" → 上下文中有"2小时" → 修正为"2小时"

        :param answer: LLM生成的原始答案
        :param retrieved_docs: 检索到的参考文档
        :return: 校验修正后的答案
        """
        if not answer or not retrieved_docs:
            return answer

        # 1. 从检索上下文提取所有"数值+单位"
        ctx_text = ' '.join(d.page_content for d in retrieved_docs if d.page_content)
        ctx_numbers = self._extract_number_expressions(ctx_text)
        if not ctx_numbers:
            return answer

        # 去重并统计出现次数（出现次数越高越可信）
        ctx_count: Dict[tuple, int] = {}
        for val, unit in ctx_numbers:
            key = (round(val, 4), unit)
            ctx_count[key] = ctx_count.get(key, 0) + 1

        # 2. 从答案中提取数值表达式
        ans_numbers = self._extract_number_expressions(answer)
        if not ans_numbers:
            return answer

        # 3. 逐项校验
        modified = answer
        corrections = 0
        for ans_val, ans_unit in ans_numbers:
            ans_key = (round(ans_val, 4), ans_unit)

            # 答案中的数值在上下文中直接存在 → 跳过
            if ans_key in ctx_count:
                continue

            # 查找上下文中相近的数值（±50%范围，单位匹配，且需满足置信度）
            best_match = None
            best_score = float('inf')
            for (ctx_val, ctx_unit), count in ctx_count.items():
                if ctx_unit != ans_unit:
                    continue
                if ans_val == 0:
                    continue
                ratio = ctx_val / ans_val
                if 0.5 <= ratio <= 2.0 and ratio != 1.0:
                    # 置信度：优先高频数值 + 比例接近者
                    # 出现>=2次：高置信度；仅1次：要求比例在25%以内
                    if count < 2 and (ratio < 0.75 or ratio > 1.25):
                        continue
                    score = abs(1.0 - ratio) - count * 0.01
                    if score < best_score:
                        best_score = score
                        best_match = (ctx_val, ctx_unit)

            if best_match is None:
                continue

            ctx_val, ctx_unit = best_match

            # 构造替换：匹配原始数值表达式
            pattern_str = re.escape(str(ans_val).rstrip('0').rstrip('.')) + r'\s*' + re.escape(ans_unit)
            pattern = re.compile(pattern_str)
            replacement = f"{_format_num(ctx_val)}{ans_unit}"
            new_text = pattern.sub(replacement, modified, count=1)
            if new_text != modified:
                logger.info(f"数值校验修正: {ans_val}{ans_unit} → {_format_num(ctx_val)}{ans_unit}")
                modified = new_text
                corrections += 1

        if corrections > 0:
            logger.info(f"数值校验完成: 共修正 {corrections} 处")

        return modified

    @staticmethod
    def _extract_number_expressions(text: str) -> List[tuple]:
        """
        从文本中提取所有"数值, 单位"对

        :param text: 输入文本
        :return: [(数值, 单位), ...]
        """
        # 匹配：数字 + 可选空格 + 常见单位
        pattern = re.compile(
            r'(\d+(?:\.\d+)?)\s*'
            r'(mm|cm|m|km|℃|T|t|kg|g|%|个|处|次|点|分钟|小时|年|分|元|MPa|kPa)'
        )
        matches = pattern.findall(text)
        return [(float(m[0]), m[1]) for m in matches]

    def _should_search_web(self, local_results: List[Document]) -> bool:
        """
        判断是否需要网络检索

        :param local_results: 本地检索结果
        :return: 是否需要网络检索
        """
        if not local_results:
            return True
        return len(local_results) < 3

    def _extract_sources(self, docs: List[Document]) -> List[SourceInfo]:
        """
        提取来源信息

        :param docs: Document列表
        :return: 来源信息列表
        """
        sources = []
        seen_chunk_ids = set()

        for doc in docs:
            metadata = doc.metadata
            chunk_id = metadata.get("chunk_id", "")

            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)

            source_type = SourceType.WEB if metadata.get("source_type") == "web" else SourceType.LOCAL

            content = doc.page_content
            if len(content) > 500:
                content = content[:500] + "..."

            source = SourceInfo(
                chunk_id=chunk_id or f"doc_{hash(doc.page_content) % 1000000:06d}",
                doc_id=metadata.get("doc_id", ""),
                doc_name=metadata.get("doc_name", ""),
                page=metadata.get("page"),
                section=metadata.get("section"),
                content=content,
                source_type=source_type,
                url=metadata.get("url") if source_type == SourceType.WEB else None,
            )
            sources.append(source)

        return sources


_orchestrator_instance: Optional[QueryOrchestrator] = None


def get_orchestrator() -> QueryOrchestrator:
    """
    获取QueryOrchestrator单例

    :return: QueryOrchestrator实例
    """
    global _orchestrator_instance

    if _orchestrator_instance is None:
        _orchestrator_instance = QueryOrchestrator()

    return _orchestrator_instance
