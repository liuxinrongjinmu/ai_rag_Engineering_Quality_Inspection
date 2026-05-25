"""
文本切片器
将Document内容切分为适当大小的片段
保留表格内容完整性
"""
from typing import List, Dict, Any, Optional
from loguru import logger
import re
import hashlib

from langchain_core.documents import Document


class TextChunker:
    """
    文本切片器
    支持按段落和固定大小切分，保留表格完整性
    """

    TABLE_PATTERN = re.compile(r'^\|.*\|$', re.MULTILINE)

    MAX_EMBEDDING_LENGTH = 2000

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
        self.chunk_size = min(chunk_size, self.MAX_EMBEDDING_LENGTH)
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        切分Document列表

        :param documents: 原始Document列表
        :return: 切分后的Document列表
        """
        all_chunks = []
        chunk_index = 0

        for doc in documents:
            chunks = self._split_single_document(doc, chunk_index)
            all_chunks.extend(chunks)
            chunk_index += len(chunks)

        logger.info(f"切片完成: {len(documents)}个文档 -> {len(all_chunks)}个切片")
        return all_chunks

    def _split_single_document(
        self,
        document: Document,
        start_index: int
    ) -> List[Document]:
        """
        切分单个Document

        :param document: 原始Document
        :param start_index: 起始索引
        :return: 切分后的Document列表
        """
        text = document.page_content
        metadata = document.metadata.copy()

        if not text or not text.strip():
            return []

        tables = self._extract_tables(text)
        non_table_text = self._remove_tables(text, tables)

        chunks = []
        chunk_index = start_index

        for table in tables:
            table_text = table.strip()
            if len(table_text) < self.min_chunk_size:
                continue

            if len(table_text) <= self.MAX_EMBEDDING_LENGTH:
                chunk_metadata = metadata.copy()
                chunk_metadata["chunk_index"] = chunk_index
                chunk_metadata["is_table"] = True
                chunk_metadata["chunk_id"] = self._generate_chunk_id(
                    metadata.get("doc_id", ""), chunk_index
                )
                chunks.append(Document(
                    page_content=table_text,
                    metadata=chunk_metadata,
                ))
                chunk_index += 1
            else:
                table_chunks = self._split_table(table_text, metadata, chunk_index)
                chunks.extend(table_chunks)
                chunk_index += len(table_chunks)

        paragraphs = self._split_paragraphs(non_table_text)
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) <= self.chunk_size:
                current_chunk += para + "\n"
            else:
                if current_chunk.strip():
                    chunk_metadata = metadata.copy()
                    chunk_metadata["chunk_index"] = chunk_index
                    chunk_metadata["chunk_id"] = self._generate_chunk_id(
                        metadata.get("doc_id", ""), chunk_index
                    )
                    chunks.append(Document(
                        page_content=current_chunk.strip(),
                        metadata=chunk_metadata,
                    ))
                    chunk_index += 1

                if len(para) > self.chunk_size:
                    sub_chunks = self._chunk_large_paragraph(
                        para, metadata, chunk_index
                    )
                    chunks.extend(sub_chunks)
                    chunk_index += len(sub_chunks)
                    current_chunk = ""
                else:
                    overlap_text = self._get_overlap_text(current_chunk)
                    current_chunk = overlap_text + para + "\n"

        if current_chunk.strip():
            chunk_metadata = metadata.copy()
            chunk_metadata["chunk_index"] = chunk_index
            chunk_metadata["chunk_id"] = self._generate_chunk_id(
                metadata.get("doc_id", ""), chunk_index
            )
            content = current_chunk.strip()
            if len(content) > self.MAX_EMBEDDING_LENGTH:
                content = content[:self.MAX_EMBEDDING_LENGTH]
            chunks.append(Document(
                page_content=content,
                metadata=chunk_metadata,
            ))

        final_chunks = []
        for chunk in chunks:
            if len(chunk.page_content) <= self.MAX_EMBEDDING_LENGTH:
                final_chunks.append(chunk)
            else:
                sub = self._chunk_large_paragraph(
                    chunk.page_content, chunk.metadata, chunk.metadata["chunk_index"]
                )
                final_chunks.extend(sub)

        return final_chunks

    def _split_table(
        self,
        table_text: str,
        metadata: Dict[str, Any],
        start_index: int
    ) -> List[Document]:
        """
        切分大表格

        :param table_text: 表格文本
        :param metadata: 元数据
        :param start_index: 起始索引
        :return: 切片列表
        """
        lines = table_text.split('\n')
        header_lines = []
        data_lines = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if i < 3 or '---' in stripped:
                header_lines.append(line)
            else:
                data_lines.append(line)

        header_text = '\n'.join(header_lines) + '\n' if header_lines else ''
        header_len = len(header_text)

        chunks = []
        current_lines = []
        current_len = header_len
        chunk_index = start_index

        for line in data_lines:
            if current_len + len(line) + 1 > self.MAX_EMBEDDING_LENGTH and current_lines:
                content = header_text + '\n'.join(current_lines)
                chunk_metadata = metadata.copy()
                chunk_metadata["chunk_index"] = chunk_index
                chunk_metadata["is_table"] = True
                chunk_metadata["chunk_id"] = self._generate_chunk_id(
                    metadata.get("doc_id", ""), chunk_index
                )
                chunks.append(Document(
                    page_content=content.strip(),
                    metadata=chunk_metadata,
                ))
                chunk_index += 1
                current_lines = []
                current_len = header_len

            current_lines.append(line)
            current_len += len(line) + 1

        if current_lines:
            content = header_text + '\n'.join(current_lines)
            chunk_metadata = metadata.copy()
            chunk_metadata["chunk_index"] = chunk_index
            chunk_metadata["is_table"] = True
            chunk_metadata["chunk_id"] = self._generate_chunk_id(
                metadata.get("doc_id", ""), chunk_index
            )
            chunks.append(Document(
                page_content=content.strip(),
                metadata=chunk_metadata,
            ))

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
    ) -> List[Document]:
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
                    chunk_metadata = metadata.copy()
                    chunk_metadata["chunk_index"] = chunk_index
                    chunk_metadata["chunk_id"] = self._generate_chunk_id(
                        metadata.get("doc_id", ""), chunk_index
                    )
                    chunks.append(Document(
                        page_content=current_chunk.strip(),
                        metadata=chunk_metadata,
                    ))
                    chunk_index += 1

                overlap_text = self._get_overlap_text(current_chunk)
                current_chunk = overlap_text + sentence

        if current_chunk.strip():
            chunk_metadata = metadata.copy()
            chunk_metadata["chunk_index"] = chunk_index
            chunk_metadata["chunk_id"] = self._generate_chunk_id(
                metadata.get("doc_id", ""), chunk_index
            )
            chunks.append(Document(
                page_content=current_chunk.strip(),
                metadata=chunk_metadata,
            ))

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

    def _generate_chunk_id(self, doc_id: str, index: int) -> str:
        """
        生成切片ID

        :param doc_id: 文档ID
        :param index: 索引
        :return: 切片ID
        """
        unique_str = f"{doc_id}_{index}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:16]
