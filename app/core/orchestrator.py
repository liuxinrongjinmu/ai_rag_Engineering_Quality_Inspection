"""
查询编排器
协调整个问答流程
"""
from typing import Dict, Any, Optional, Generator
from loguru import logger
from pathlib import Path
import time

from app.config import get_settings
from app.core.hybrid_retriever import HybridRetriever, get_hybrid_retriever
from app.core.rag_engine import RAGEngine, get_rag_engine
from app.retrievers.local_retriever import get_local_retriever
from app.retrievers.bm25_retriever import get_bm25_retriever
from app.models.response import QueryData, SourceInfo
from app.utils.cache import get_query_cache


class QueryOrchestrator:
    """
    查询编排器
    协调检索、重排序、生成流程
    """
    
    def __init__(
        self,
        hybrid_retriever: Optional[HybridRetriever] = None,
        rag_engine: Optional[RAGEngine] = None
    ):
        """
        初始化查询编排器
        
        :param hybrid_retriever: 混合检索器
        :param rag_engine: RAG引擎
        """
        self.hybrid_retriever = hybrid_retriever
        self.rag_engine = rag_engine
        self.settings = get_settings()
    
    def initialize(self) -> bool:
        """
        初始化组件
        
        :return: 是否成功
        """
        if self.hybrid_retriever is None:
            self.hybrid_retriever = get_hybrid_retriever(
                top_k=self.settings.TOP_K_RESULTS,
                use_web_search=True
            )
        
        if self.rag_engine is None:
            self.rag_engine = get_rag_engine()
        
        # 加载BM25索引
        self._load_bm25_index()
        
        return True
    
    def _load_bm25_index(self):
        """
        加载BM25索引
        """
        bm25_path = Path(self.settings.BM25_INDEX_PATH)
        
        if bm25_path.exists():
            bm25_retriever = get_bm25_retriever()
            if bm25_retriever.load(str(bm25_path)):
                logger.info("BM25索引加载成功")
            else:
                logger.warning("BM25索引加载失败")
        else:
            logger.warning(f"BM25索引文件不存在: {bm25_path}")
    
    def process_query(
        self,
        question: str,
        use_web_search: bool = True,
        top_k: int = 5,
        use_cache: bool = True
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
        
        self.initialize()
        
        logger.info(f"处理查询: {question[:50]}...")
        
        if use_cache:
            cache = get_query_cache()
            cached_result = cache.get(question, use_web_search)
            
            if cached_result:
                cached_result['query_time_ms'] = int((time.time() - start_time) * 1000)
                cached_result['used_web_search'] = cached_result.get('used_web_search', False)
                logger.info(f"缓存命中，返回缓存结果")
                return QueryData(**cached_result)
        
        retrieval_result = self.hybrid_retriever.retrieve(
            query=question,
            use_web_search=use_web_search
        )
        
        results = retrieval_result["results"]
        used_web_search = retrieval_result["used_web_search"]
        rewritten_query = retrieval_result.get("rewritten_query")
        
        if rewritten_query:
            logger.info(f"查询已重写: {rewritten_query}")
        
        if not results:
            query_time = int((time.time() - start_time) * 1000)
            return QueryData(
                answer="抱歉，没有找到相关的信息来回答您的问题。请尝试换一种方式提问。",
                sources=[],
                query_time_ms=query_time,
                used_web_search=False
            )
        
        generation_result = self.rag_engine.generate(
            query=question,
            results=results
        )
        
        answer = generation_result["answer"]
        
        sources = self.rag_engine.extract_sources(results)
        
        query_time = int((time.time() - start_time) * 1000)
        
        logger.info(f"查询完成: 耗时{query_time}ms")
        
        result_data = QueryData(
            answer=answer,
            sources=sources,
            query_time_ms=query_time,
            used_web_search=used_web_search
        )
        
        if use_cache:
            cache = get_query_cache()
            cache.set(
                question=question,
                data=result_data.model_dump(),
                use_web_search=use_web_search
            )
        
        return result_data
    
    def get_source_detail(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        获取来源详情
        
        :param chunk_id: 切片ID
        :return: 来源详情
        """
        self.initialize()
        
        local_retriever = get_local_retriever()
        chunk = local_retriever.get_by_id(chunk_id)
        
        if not chunk:
            return None
        
        context = local_retriever.get_context(chunk_id)
        
        return {
            "chunk_id": chunk_id,
            "doc_id": chunk.doc_id,
            "doc_name": chunk.doc_name,
            "page": chunk.page,
            "section": chunk.section,
            "full_content": chunk.content,
            "context_before": context.get("before"),
            "context_after": context.get("after")
        }


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
