"""
向量数据库模块
使用ChromaDB进行向量存储和检索
"""
from typing import List, Dict, Any, Optional
from loguru import logger
import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions
from pathlib import Path
import json


class VectorStore:
    """
    向量数据库封装类
    """
    
    def __init__(
        self,
        persist_directory: str = "./data/vectordb",
        collection_name: str = "engineering_qa"
    ):
        """
        初始化向量数据库
        
        :param persist_directory: 持久化目录
        :param collection_name: 集合名称
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        
        self.client: Optional[chromadb.Client] = None
        self.collection: Optional[chromadb.Collection] = None
        self._initialized = False
    
    def initialize(self) -> bool:
        """
        初始化数据库连接
        
        :return: 是否成功初始化
        """
        try:
            self.client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            
            self._initialized = True
            logger.info(f"向量数据库初始化成功: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"向量数据库初始化失败: {e}")
            return False
    
    def is_initialized(self) -> bool:
        """
        检查是否已初始化
        
        :return: 是否已初始化
        """
        return self._initialized and self.collection is not None
    
    def _clean_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        清理metadata，确保所有值都是有效类型
        
        :param metadata: 原始metadata
        :return: 清理后的metadata
        """
        cleaned = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                cleaned[key] = value
            elif isinstance(value, dict):
                cleaned[key] = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, list):
                cleaned[key] = json.dumps(value, ensure_ascii=False)
            else:
                cleaned[key] = str(value)
        return cleaned
    
    def add_chunks(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> int:
        """
        添加切片到向量数据库
        
        :param chunks: 切片列表（需包含embedding）
        :param batch_size: 批次大小
        :return: 成功添加的数量
        """
        if not self.is_initialized():
            logger.warning("向量数据库未初始化")
            return 0
        
        added_count = 0
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            ids = []
            embeddings = []
            documents = []
            metadatas = []
            
            for chunk in batch:
                if "embedding" not in chunk:
                    continue
                
                ids.append(chunk["chunk_id"])
                embeddings.append(chunk["embedding"])
                documents.append(chunk["content"])
                
                metadata = {
                    "doc_id": chunk.get("doc_id", ""),
                    "doc_name": chunk.get("doc_name", ""),
                    "page": chunk.get("page", 0) if chunk.get("page") else 0,
                    "section": chunk.get("section", ""),
                    "source_type": chunk.get("source_type", "local")
                }
                metadata.update(chunk.get("metadata", {}))
                metadatas.append(self._clean_metadata(metadata))
            
            if ids:
                try:
                    self.collection.add(
                        ids=ids,
                        embeddings=embeddings,
                        documents=documents,
                        metadatas=metadatas
                    )
                    added_count += len(ids)
                except Exception as e:
                    logger.error(f"添加切片失败: {e}")
        
        logger.info(f"添加切片完成: {added_count}个")
        return added_count
    
    def query(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        向量检索
        
        :param query_embedding: 查询向量
        :param top_k: 返回数量
        :param where: 元数据过滤条件
        :return: 检索结果
        """
        if not self.is_initialized():
            logger.warning("向量数据库未初始化")
            return {"ids": [], "documents": [], "metadatas": [], "distances": []}
        
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"]
            )
            return results
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return {"ids": [], "documents": [], "metadatas": [], "distances": []}
    
    def get_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取切片
        
        :param chunk_id: 切片ID
        :return: 切片数据
        """
        if not self.is_initialized():
            return None
        
        try:
            results = self.collection.get(
                ids=[chunk_id],
                include=["documents", "metadatas", "embeddings"]
            )
            
            if results["ids"]:
                return {
                    "chunk_id": chunk_id,
                    "content": results["documents"][0],
                    "metadata": results["metadatas"][0],
                    "embedding": results["embeddings"][0] if results.get("embeddings") else None
                }
            return None
        except Exception as e:
            logger.error(f"获取切片失败: {e}")
            return None
    
    def delete_by_doc_id(self, doc_id: str) -> bool:
        """
        根据文档ID删除切片
        
        :param doc_id: 文档ID
        :return: 是否成功
        """
        if not self.is_initialized():
            return False
        
        try:
            results = self.collection.get(
                where={"doc_id": doc_id}
            )
            
            if results["ids"]:
                self.collection.delete(ids=results["ids"])
                logger.info(f"删除文档切片: {doc_id}, 数量: {len(results['ids'])}")
            
            return True
        except Exception as e:
            logger.error(f"删除切片失败: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        :return: 统计信息
        """
        if not self.is_initialized():
            return {"total_chunks": 0, "total_docs": 0}
        
        try:
            count = self.collection.count()
            
            results = self.collection.get(include=["metadatas"])
            doc_ids = set()
            if results["metadatas"]:
                for meta in results["metadatas"]:
                    if "doc_id" in meta:
                        doc_ids.add(meta["doc_id"])
            
            return {
                "total_chunks": count,
                "total_docs": len(doc_ids),
                "doc_ids": list(doc_ids)
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {"total_chunks": 0, "total_docs": 0}
    
    def reset(self) -> bool:
        """
        重置集合
        
        :return: 是否成功
        """
        if not self.is_initialized():
            return False
        
        try:
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"集合已重置: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"重置集合失败: {e}")
            return False


_vectorstore_instance: Optional[VectorStore] = None


def get_vectorstore(
    persist_directory: str = "./data/vectordb",
    collection_name: str = "engineering_qa"
) -> VectorStore:
    """
    获取VectorStore单例
    
    :param persist_directory: 持久化目录
    :param collection_name: 集合名称
    :return: VectorStore实例
    """
    global _vectorstore_instance
    
    if _vectorstore_instance is None:
        _vectorstore_instance = VectorStore(persist_directory, collection_name)
        _vectorstore_instance.initialize()
    
    return _vectorstore_instance
