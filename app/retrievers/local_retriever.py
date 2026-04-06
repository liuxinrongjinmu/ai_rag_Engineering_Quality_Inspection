"""
本地检索器
从Milvus向量数据库检索相关内容
"""
from typing import List, Dict, Any, Optional
from loguru import logger
import numpy as np

from app.config import get_settings
from app.retrievers.vector_store import VectorStore, get_vectorstore
from app.processors.embedder import Embedder, get_embedder
from app.models.document import Chunk, SearchResult, SourceType


class LocalRetriever:
    """
    本地知识库检索器
    """
    
    def __init__(
        self,
        vectorstore: Optional[VectorStore] = None,
        embedder: Optional[Embedder] = None,
        top_k: int = 5
    ):
        """
        初始化本地检索器
        
        :param vectorstore: 向量数据库
        :param embedder: 向量化器
        :param top_k: 返回结果数
        """
        self.vectorstore = vectorstore
        self.embedder = embedder
        self.top_k = top_k
    
    def initialize(self) -> bool:
        """
        初始化组件
        
        :return: 是否成功
        """
        settings = get_settings()
        
        if self.vectorstore is None:
            self.vectorstore = get_vectorstore(
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT,
                collection_name=settings.MILVUS_COLLECTION_NAME,
                embedding_dim=settings.EMBEDDING_DIM
            )
        
        if self.embedder is None:
            self.embedder = get_embedder()
        
        return self.vectorstore.is_initialized() and self.embedder.is_initialized()
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict] = None
    ) -> List[SearchResult]:
        """
        检索相关内容
        
        :param query: 查询文本
        :param top_k: 返回结果数
        :param filters: 元数据过滤条件
        :return: 检索结果列表
        """
        if not self.initialize():
            logger.warning("本地检索器未初始化")
            return []
        
        top_k = top_k or self.top_k
        
        query_embedding = self.embedder.embed_text(query)
        if query_embedding is None:
            logger.warning("查询向量化失败")
            return []
        
        results = self.vectorstore.query(
            query_embedding=query_embedding.tolist(),
            top_k=top_k,
            where=filters
        )
        
        search_results = []
        if results["ids"]:
            for i, chunk_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i] if results.get("metadatas") else {}
                document = results["documents"][i] if results.get("documents") else ""
                distance = results["distances"][i] if results.get("distances") else 0
                
                score = max(0.0, min(1.0, distance))
                
                chunk = Chunk(
                    chunk_id=chunk_id,
                    doc_id=metadata.get("doc_id", ""),
                    doc_name=metadata.get("doc_name", ""),
                    content=document,
                    page=metadata.get("page"),
                    section=metadata.get("section"),
                    source_type=SourceType.LOCAL,
                    metadata=metadata
                )
                
                search_results.append(SearchResult(
                    chunk=chunk,
                    score=score
                ))
        
        logger.info(f"本地检索完成: 查询='{query[:30]}...', 结果数={len(search_results)}, 最高分={max([r.score for r in search_results]) if search_results else 0:.3f}")
        return search_results
    
    def get_by_id(self, chunk_id: str) -> Optional[Chunk]:
        """
        根据ID获取切片
        
        :param chunk_id: 切片ID
        :return: 切片对象
        """
        if not self.initialize():
            return None
        
        result = self.vectorstore.get_by_id(chunk_id)
        if result:
            metadata = result.get("metadata", {})
            return Chunk(
                chunk_id=chunk_id,
                doc_id=metadata.get("doc_id", ""),
                doc_name=metadata.get("doc_name", ""),
                content=result.get("content", ""),
                page=metadata.get("page"),
                section=metadata.get("section"),
                source_type=SourceType.LOCAL,
                metadata=metadata
            )
        return None
    
    def get_context(
        self,
        chunk_id: str,
        context_size: int = 2
    ) -> Dict[str, Optional[str]]:
        """
        获取切片上下文
        
        :param chunk_id: 切片ID
        :param context_size: 上下文大小
        :return: 上下文信息
        """
        chunk = self.get_by_id(chunk_id)
        if not chunk:
            return {"before": None, "after": None, "current": None}
        
        return {
            "current": chunk.content,
            "before": None,
            "after": None
        }


_local_retriever_instance: Optional[LocalRetriever] = None


def get_local_retriever(top_k: int = 5) -> LocalRetriever:
    """
    获取LocalRetriever单例
    
    :param top_k: 返回结果数
    :return: LocalRetriever实例
    """
    global _local_retriever_instance
    
    if _local_retriever_instance is None:
        _local_retriever_instance = LocalRetriever(top_k=top_k)
    
    return _local_retriever_instance
