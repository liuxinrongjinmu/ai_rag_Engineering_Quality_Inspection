"""
向量数据库模块
使用ChromaDB进行向量存储和检索
"""
from typing import List, Dict, Any, Optional
from loguru import logger
from pathlib import Path
import chromadb
from chromadb.config import Settings as ChromaSettings


class VectorStore:
    """
    向量数据库封装类 - ChromaDB实现
    """
    
    def __init__(
        self,
        persist_dir: str = "./data/vectordb/chroma",
        collection_name: str = "engineering_qa",
        embedding_dim: int = 1536
    ):
        """
        初始化向量数据库
        
        :param persist_dir: ChromaDB数据持久化目录
        :param collection_name: 集合名称
        :param embedding_dim: 向量维度
        """
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        
        self.client: Optional[chromadb.Client] = None
        self.collection: Optional[chromadb.Collection] = None
        self._initialized = False
    
    def initialize(self) -> bool:
        """
        初始化数据库连接
        
        :return: 是否成功初始化
        """
        try:
            persist_path = Path(self.persist_dir)
            persist_path.mkdir(parents=True, exist_ok=True)
            
            self.client = chromadb.PersistentClient(
                path=str(persist_path),
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
            logger.info(f"ChromaDB连接成功: {self.persist_dir}, 集合: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"ChromaDB连接失败: {e}")
            return False
    
    def is_initialized(self) -> bool:
        """
        检查是否已初始化
        
        :return: 是否已初始化
        """
        return self._initialized and self.collection is not None
    
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
                
                chunk_id = chunk.get("chunk_id", "")
                if not chunk_id:
                    continue
                
                ids.append(chunk_id)
                embeddings.append(chunk["embedding"])
                documents.append(chunk.get("content", ""))
                
                metadata = {
                    "doc_id": chunk.get("doc_id", ""),
                    "doc_name": chunk.get("doc_name", ""),
                    "page": chunk.get("page", 0) or 0,
                    "section": chunk.get("section", "") or "",
                    "source_type": chunk.get("source_type", "local") or "local"
                }
                metadatas.append(metadata)
            
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
            
            ids = results.get("ids", [[]])[0]
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            
            return {
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
                "distances": [1 - d for d in distances]  # ChromaDB返回距离，转换为相似度
            }
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
            
            if results and results.get("ids"):
                return {
                    "chunk_id": chunk_id,
                    "content": results["documents"][0] if results.get("documents") else "",
                    "metadata": results["metadatas"][0] if results.get("metadatas") else {},
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
                where={"doc_id": doc_id},
                include=[]
            )
            
            if results and results.get("ids"):
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
            
            results = self.collection.get(
                include=["metadatas"]
            )
            
            doc_ids = set()
            if results and results.get("metadatas"):
                for metadata in results["metadatas"]:
                    if metadata.get("doc_id"):
                        doc_ids.add(metadata.get("doc_id"))
            
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
    persist_dir: str = "./data/vectordb/chroma",
    collection_name: str = "engineering_qa",
    embedding_dim: int = 1536
) -> VectorStore:
    """
    获取VectorStore单例
    
    :param persist_dir: ChromaDB数据持久化目录
    :param collection_name: 集合名称
    :param embedding_dim: 向量维度
    :return: VectorStore实例
    """
    global _vectorstore_instance
    
    if _vectorstore_instance is None:
        _vectorstore_instance = VectorStore(persist_dir, collection_name, embedding_dim)
        _vectorstore_instance.initialize()
    
    return _vectorstore_instance
