"""
文本切片器
将文档内容切分为适当大小的片段
优化表格内容处理
"""
from typing import List, Dict, Any, Optional
from loguru import logger
import re
import hashlib


class TextChunker:
    """
    文本切片器
    支持按段落和固定大小切分，优化表格处理
    """
    
    # 表格检测正则
    TABLE_PATTERN = re.compile(r'^\|.*\|$', re.MULTILINE)
    TABLE_ROW_PATTERN = re.compile(r'^\|(.+)\|$')
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100
    ):
        """
        初始化切片器
        
        :param chunk_size: 切片大小（字符数）
        :param chunk_overlap: 切片重叠（字符数）
        :param min_chunk_size: 最小切片大小
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
    
    def chunk_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        切分文本
        
        :param text: 待切分文本
        :param metadata: 元数据
        :return: 切片列表
        """
        if not text or not text.strip():
            return []
        
        metadata = metadata or {}
        
        # 检测表格内容
        tables = self._extract_tables(text)
        non_table_text = self._remove_tables(text, tables)
        
        chunks = []
        chunk_index = 0
        
        # 处理表格（每个表格作为一个独立切片）
        for table in tables:
            if len(table.strip()) >= self.min_chunk_size:
                chunk = self._create_chunk(
                    table.strip(),
                    chunk_index,
                    metadata
                )
                chunk["is_table"] = True
                chunks.append(chunk)
                chunk_index += 1
        
        # 处理非表格文本
        paragraphs = self._split_paragraphs(non_table_text)
        
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) <= self.chunk_size:
                current_chunk += para + "\n"
            else:
                if current_chunk.strip():
                    chunk = self._create_chunk(
                        current_chunk.strip(),
                        chunk_index,
                        metadata
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                
                if len(para) > self.chunk_size:
                    sub_chunks = self._chunk_large_paragraph(para, metadata, chunk_index)
                    chunks.extend(sub_chunks)
                    chunk_index += len(sub_chunks)
                    current_chunk = ""
                else:
                    overlap_text = self._get_overlap_text(current_chunk)
                    current_chunk = overlap_text + para + "\n"
        
        if current_chunk.strip():
            chunk = self._create_chunk(
                current_chunk.strip(),
                chunk_index,
                metadata
            )
            chunks.append(chunk)
        
        # 按原始顺序重新排序
        chunks.sort(key=lambda x: text.find(x["content"][:50]) if x["content"][:50] in text else 999999)
        
        return chunks
    
    def _extract_tables(self, text: str) -> List[str]:
        """
        提取表格内容
        
        :param text: 原始文本
        :return: 表格列表
        """
        tables = []
        lines = text.split('\n')
        
        current_table = []
        in_table = False
        
        for line in lines:
            if self.TABLE_PATTERN.match(line.strip()):
                in_table = True
                current_table.append(line)
            else:
                if in_table and current_table:
                    tables.append('\n'.join(current_table))
                    current_table = []
                in_table = False
        
        if current_table:
            tables.append('\n'.join(current_table))
        
        return tables
    
    def _remove_tables(self, text: str, tables: List[str]) -> str:
        """
        移除表格内容
        
        :param text: 原始文本
        :param tables: 表格列表
        :return: 移除表格后的文本
        """
        result = text
        for table in tables:
            result = result.replace(table, '')
        return result
    
    def chunk_pdf_pages(
        self,
        pages: List[Dict[str, Any]],
        doc_id: str,
        doc_name: str
    ) -> List[Dict[str, Any]]:
        """
        切分PDF页面内容
        
        :param pages: 页面内容列表
        :param doc_id: 文档ID
        :param doc_name: 文档名称
        :return: 切片列表
        """
        all_chunks = []
        chunk_index = 0
        
        for page in pages:
            page_num = page.get("page", 0)
            content = page.get("content", "")
            
            if not content.strip():
                continue
            
            metadata = {
                "doc_id": doc_id,
                "doc_name": doc_name,
                "page": page_num,
                "source_type": "local"
            }
            
            page_chunks = self.chunk_text(content, metadata)
            
            for chunk in page_chunks:
                chunk["chunk_id"] = self._generate_chunk_id(doc_id, chunk_index)
                chunk_index += 1
                all_chunks.append(chunk)
        
        logger.info(f"PDF切片完成: {doc_name}, 共{len(all_chunks)}个切片")
        return all_chunks
    
    def chunk_excel_records(
        self,
        records: List[Dict[str, Any]],
        doc_id: str,
        doc_name: str
    ) -> List[Dict[str, Any]]:
        """
        切分Excel记录
        
        :param records: 记录列表
        :param doc_id: 文档ID
        :param doc_name: 文档名称
        :return: 切片列表
        """
        chunks = []
        
        for idx, record in enumerate(records):
            content = record.get("content", "")
            if not content.strip():
                continue
            
            chunk = {
                "chunk_id": self._generate_chunk_id(doc_id, idx),
                "doc_id": doc_id,
                "doc_name": doc_name,
                "content": content,
                "page": None,
                "section": None,
                "source_type": "local",
                "metadata": {
                    "row_index": record.get("row_index"),
                    "raw_data": record.get("raw_data", {})
                }
            }
            chunks.append(chunk)
        
        logger.info(f"Excel切片完成: {doc_name}, 共{len(chunks)}个切片")
        return chunks
    
    def _split_paragraphs(self, text: str) -> List[str]:
        """
        按段落分割文本
        
        :param text: 原始文本
        :return: 段落列表
        """
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def _chunk_large_paragraph(
        self,
        text: str,
        metadata: Dict[str, Any],
        start_index: int
    ) -> List[Dict[str, Any]]:
        """
        切分大段落
        
        :param text: 大段落文本
        :param metadata: 元数据
        :param start_index: 起始索引
        :return: 切片列表
        """
        chunks = []
        sentences = self._split_sentences(text)
        
        current_chunk = ""
        chunk_index = start_index
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= self.chunk_size:
                current_chunk += sentence
            else:
                if current_chunk.strip():
                    chunk = self._create_chunk(
                        current_chunk.strip(),
                        chunk_index,
                        metadata
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                
                overlap_text = self._get_overlap_text(current_chunk)
                current_chunk = overlap_text + sentence
        
        if current_chunk.strip():
            chunk = self._create_chunk(
                current_chunk.strip(),
                chunk_index,
                metadata
            )
            chunks.append(chunk)
        
        return chunks
    
    def _split_sentences(self, text: str) -> List[str]:
        """
        按句子分割文本
        
        :param text: 原始文本
        :return: 句子列表
        """
        sentences = re.split(r'([。！？；\n])', text)
        result = []
        for i in range(0, len(sentences) - 1, 2):
            if i + 1 < len(sentences):
                result.append(sentences[i] + sentences[i + 1])
            else:
                result.append(sentences[i])
        
        if len(sentences) % 2 == 1 and sentences[-1].strip():
            result.append(sentences[-1])
        
        return result
    
    def _get_overlap_text(self, text: str) -> str:
        """
        获取重叠文本
        
        :param text: 原始文本
        :return: 重叠部分
        """
        if len(text) <= self.chunk_overlap:
            return text
        
        overlap = text[-self.chunk_overlap:]
        
        match = re.search(r'[。！？；]', overlap)
        if match:
            overlap = overlap[match.end():]
        
        return overlap
    
    def _create_chunk(
        self,
        content: str,
        index: int,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建切片对象
        
        :param content: 内容
        :param index: 索引
        :param metadata: 元数据
        :return: 切片对象
        """
        return {
            "content": content,
            "index": index,
            "metadata": metadata.copy()
        }
    
    def _generate_chunk_id(self, doc_id: str, index: int) -> str:
        """
        生成切片ID
        
        :param doc_id: 文档ID
        :param index: 索引
        :return: 切片ID
        """
        unique_str = f"{doc_id}_{index}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:16]
