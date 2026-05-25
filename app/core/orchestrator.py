"""
查询编排器
协调整个问答流程：缓存→检索→重排序→RAG Chain→来源提取
"""
from typing import Dict, Any, Optional, List, Generator
from loguru import logger
import time

from langchain_core.documents import Document

from app.config import get_settings
from app.chains.rag_chain import invoke_rag, stream_rag
from app.retrievers.ensemble_retriever import hybrid_retrieve
from app.retrievers.web_retriever import search_web
from app.retrievers.reranker import get_reranker
from app.processors.query_rewriter import get_query_rewriter
from app.utils.cache import get_query_cache
from app.models.response import QueryData, SourceInfo
from app.models.document import SourceType


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

    def process_query(
        self,
        question: str,
        use_web_search: bool = True,
        top_k: int = 5,
        use_cache: bool = True,
    ) -> QueryData:
        """
        处理查询（带缓存优化）

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

        # 1. 查询重写
        query_rewriter = get_query_rewriter(api_key=self.settings.DASHSCOPE_API_KEY)
        rewritten_query = query_rewriter.rewrite(question)
        if rewritten_query != question:
            logger.info(f"查询已重写: {rewritten_query}")

        # 2. 混合检索
        local_results = hybrid_retrieve(rewritten_query, top_k=top_k * 2)

        # 3. 判断是否需要网络检索
        web_results: List[Document] = []
        used_web_search = False

        if use_web_search and self._should_search_web(local_results):
            try:
                web_results = search_web(question, max_results=top_k)
                used_web_search = len(web_results) > 0
            except Exception as e:
                logger.warning(f"网络检索失败: {e}")

        # 4. 重排序
        reranker = get_reranker(
            local_weight=self.settings.LOCAL_WEIGHT,
            web_weight=self.settings.WEB_WEIGHT,
        )
        final_results = reranker.rerank(
            local_results=local_results[:top_k],
            web_results=web_results,
            top_k=top_k,
        )

        if not final_results:
            query_time = int((time.time() - start_time) * 1000)
            return QueryData(
                answer="抱歉，没有找到相关的信息来回答您的问题。请尝试换一种方式提问。",
                sources=[],
                query_time_ms=query_time,
                used_web_search=False,
            )

        # 5. RAG生成
        answer = invoke_rag(question, final_results)

        # 6. 提取来源
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

    def process_query_stream(
        self,
        question: str,
        use_web_search: bool = True,
        top_k: int = 5,
    ) -> Generator[str, None, None]:
        """
        流式处理查询

        :param question: 用户问题
        :param use_web_search: 是否使用网络检索
        :param top_k: 返回结果数
        :yield: 生成的文本片段
        """
        logger.info(f"流式处理查询: {question[:50]}...")

        # 1. 查询重写
        query_rewriter = get_query_rewriter(api_key=self.settings.DASHSCOPE_API_KEY)
        rewritten_query = query_rewriter.rewrite(question)

        # 2. 混合检索
        local_results = hybrid_retrieve(rewritten_query, top_k=top_k * 2)

        # 3. 网络检索
        web_results: List[Document] = []
        if use_web_search and self._should_search_web(local_results):
            try:
                web_results = search_web(question, max_results=top_k)
            except Exception as e:
                logger.warning(f"网络检索失败: {e}")

        # 4. 重排序
        reranker = get_reranker(
            local_weight=self.settings.LOCAL_WEIGHT,
            web_weight=self.settings.WEB_WEIGHT,
        )
        final_results = reranker.rerank(
            local_results=local_results[:top_k],
            web_results=web_results,
            top_k=top_k,
        )

        if not final_results:
            yield "抱歉，没有找到相关的信息来回答您的问题。"
            return

        # 5. 流式生成
        for chunk in stream_rag(question, final_results):
            yield chunk

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

            return {
                "chunk_id": chunk_id,
                "doc_id": metadata.get("doc_id", ""),
                "doc_name": metadata.get("doc_name", ""),
                "page": metadata.get("page"),
                "section": metadata.get("section"),
                "full_content": content,
                "context_before": None,
                "context_after": None,
            }

        except Exception as e:
            logger.error(f"获取来源详情失败: {e}")
            return None

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
