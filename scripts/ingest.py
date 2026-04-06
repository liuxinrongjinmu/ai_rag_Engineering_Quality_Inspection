"""
数据入库脚本
解析Markdown和Excel文件，使用固定大小分块后存入ChromaDB向量数据库
同时初始化BM25索引
"""
import sys
from pathlib import Path
from typing import List, Dict, Any
from loguru import logger
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.processors.excel_parser import ExcelParser
from app.processors.markdown_parser import MarkdownParser
from app.processors.chunker import TextChunker
from app.processors.embedder import Embedder, get_embedder
from app.retrievers.vector_store import VectorStore
from app.retrievers.bm25_retriever import BM25Retriever, get_bm25_retriever
from app.models.document import Chunk, SourceType
from app.utils.logger import setup_logger


class DataIngestor:
    """
    数据入库管道
    使用固定大小分块，存储到ChromaDB
    """
    
    def __init__(self):
        """
        初始化入库管道
        """
        self.settings = get_settings()
        self.chunker = TextChunker(
            chunk_size=self.settings.CHUNK_SIZE,
            chunk_overlap=self.settings.CHUNK_OVERLAP
        )
        self.embedder = get_embedder()
        self.vectorstore = VectorStore(
            persist_dir=self.settings.CHROMA_PERSIST_DIR,
            collection_name=self.settings.CHROMA_COLLECTION_NAME,
            embedding_dim=self.settings.EMBEDDING_DIM
        )
        self.bm25_retriever = get_bm25_retriever()
        self.stats = {
            "total_docs": 0,
            "total_chunks": 0,
            "failed_docs": [],
            "processing_time": 0
        }
    
    def initialize(self) -> bool:
        """
        初始化组件
        
        :return: 是否成功
        """
        logger.info("正在初始化入库管道...")
        
        if not self.embedder.initialize():
            logger.error("Embedder初始化失败")
            return False
        
        if not self.vectorstore.initialize():
            logger.error("ChromaDB向量数据库初始化失败")
            return False
        
        logger.info("入库管道初始化成功")
        return True
    
    def process_excel(self, file_path: str) -> List[Dict[str, Any]]:
        """
        处理Excel文件
        
        :param file_path: 文件路径
        :return: 切片列表
        """
        logger.info(f"正在处理Excel: {Path(file_path).name}")
        
        parser = ExcelParser(file_path)
        result = parser.parse()
        
        if not result:
            logger.error(f"Excel解析失败: {file_path}")
            return []
        
        chunks = self.chunker.chunk_excel_records(
            records=result.get("records", []),
            doc_id=result["doc_id"],
            doc_name=result["doc_name"]
        )
        
        return chunks
    
    def process_markdown(self, file_path: str) -> List[Dict[str, Any]]:
        """
        处理Markdown文件
        
        :param file_path: 文件路径
        :return: 切片列表
        """
        logger.info(f"正在处理Markdown: {Path(file_path).name}")
        
        parser = MarkdownParser(file_path)
        result = parser.parse()
        
        if not result:
            logger.error(f"Markdown解析失败: {file_path}")
            return []
        
        chunks = self.chunker.chunk_pdf_pages(
            pages=result.get("pages", []),
            doc_id=result["doc_id"],
            doc_name=result["doc_name"]
        )
        
        return chunks
    
    def process_directory(self, directory: str) -> List[Dict[str, Any]]:
        """
        处理目录下所有文件
        
        :param directory: 目录路径
        :return: 所有切片列表
        """
        dir_path = Path(directory)
        all_chunks = []
        
        # 处理Markdown文件
        markdown_files = list(dir_path.glob("*.md"))
        for md_file in markdown_files:
            try:
                chunks = self.process_markdown(str(md_file))
                all_chunks.extend(chunks)
                self.stats["total_docs"] += 1
            except Exception as e:
                logger.error(f"处理Markdown失败: {md_file.name}, 错误: {e}")
                self.stats["failed_docs"].append(str(md_file))
        
        # 处理Excel文件
        excel_files = list(dir_path.glob("*.xls")) + list(dir_path.glob("*.xlsx"))
        for excel_file in excel_files:
            try:
                chunks = self.process_excel(str(excel_file))
                all_chunks.extend(chunks)
                self.stats["total_docs"] += 1
            except Exception as e:
                logger.error(f"处理Excel失败: {excel_file.name}, 错误: {e}")
                self.stats["failed_docs"].append(str(excel_file))
        
        return all_chunks
    
    def _dict_to_chunk(self, chunk_dict: Dict[str, Any]) -> Chunk:
        """
        将字典转换为Chunk对象
        
        :param chunk_dict: 切片字典
        :return: Chunk对象
        """
        return Chunk(
            chunk_id=chunk_dict.get("chunk_id", ""),
            doc_id=chunk_dict.get("doc_id", ""),
            doc_name=chunk_dict.get("doc_name", ""),
            content=chunk_dict.get("content", ""),
            page=chunk_dict.get("page"),
            section=chunk_dict.get("section"),
            source_type=SourceType.LOCAL,
            metadata=chunk_dict.get("metadata", {})
        )
    
    def ingest(self, data_dir: str) -> Dict[str, Any]:
        """
        执行入库流程
        
        :param data_dir: 数据目录
        :return: 入库统计
        """
        start_time = time.time()
        
        if not self.initialize():
            return {"success": False, "error": "初始化失败"}
        
        logger.info(f"开始处理数据目录: {data_dir}")
        
        all_chunks = self.process_directory(data_dir)
        
        if not all_chunks:
            logger.warning("没有找到可处理的数据")
            return {"success": False, "error": "没有数据"}
        
        logger.info(f"开始向量化 {len(all_chunks)} 个切片...")
        chunks_with_embeddings = self.embedder.embed_chunks(all_chunks)
        
        logger.info("开始写入ChromaDB向量数据库...")
        added_count = self.vectorstore.add_chunks(chunks_with_embeddings)
        
        # 初始化BM25索引
        logger.info("正在初始化BM25索引...")
        chunk_objects = [self._dict_to_chunk(c) for c in chunks_with_embeddings]
        self.bm25_retriever.initialize(chunk_objects)
        
        # 保存BM25索引
        bm25_path = Path(self.settings.BM25_INDEX_PATH)
        bm25_path.parent.mkdir(parents=True, exist_ok=True)
        self.bm25_retriever.save(str(bm25_path))
        
        self.stats["total_chunks"] = added_count
        self.stats["processing_time"] = round(time.time() - start_time, 2)
        
        logger.info(f"入库完成! 统计: {self.stats}")
        
        return {
            "success": True,
            "stats": self.stats
        }


def main():
    """
    主函数
    """
    setup_logger(debug=True)
    
    settings = get_settings()
    
    # 优先使用processed目录（包含Markdown文件）
    data_dir = Path(__file__).parent.parent / "data" / "processed"
    
    if not data_dir.exists():
        # 如果processed目录不存在，使用raw目录
        data_dir = Path(__file__).parent.parent / "data" / "raw"
    
    ingestor = DataIngestor()
    result = ingestor.ingest(str(data_dir))
    
    if result["success"]:
        logger.info("入库成功!")
        print(f"\n入库统计:")
        print(f"  - 处理文档数: {result['stats']['total_docs']}")
        print(f"  - 总切片数: {result['stats']['total_chunks']}")
        print(f"  - 处理时间: {result['stats']['processing_time']}秒")
        if result['stats']['failed_docs']:
            print(f"  - 失败文档: {result['stats']['failed_docs']}")
    else:
        logger.error(f"入库失败: {result.get('error')}")


if __name__ == "__main__":
    main()
