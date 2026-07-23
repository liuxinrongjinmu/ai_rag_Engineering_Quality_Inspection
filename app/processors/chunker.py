"""
文本切片器
支持文档类型感知的智能切片：
- Markdown：按标题层级切分，保留表格完整性
- PDF/Word/TXT：识别表格结构，按行切片
- Excel：保持行级记录，增强列上下文
"""
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger
import re
import hashlib

from langchain_core.documents import Document


class TextChunker:
    """
    文档类型感知文本切片器
    针对不同文档类型和内容格式采用差异化切片策略
    """

    # Markdown 表格行：以 | 开头和结尾
    MARKDOWN_TABLE_PATTERN = re.compile(r'^\|.*\|$', re.MULTILINE)

    # HTML 表格：<table>...</table>
    HTML_TABLE_PATTERN = re.compile(r'<table[^>]*>(.*?)</table>', re.DOTALL | re.IGNORECASE)
    # HTML 表格行：<tr>...</tr>
    HTML_TR_PATTERN = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
    # HTML 单元格：<td>..</td> 或 <th>..</th>
    HTML_CELL_PATTERN = re.compile(r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>', re.DOTALL | re.IGNORECASE)

    # 常见列表/条例编号
    ARTICLE_PATTERN = re.compile(r'^[（(][一二三四五六七八九十1234567890]+[）)]|^第[一二三四五六七八九十1234567890]+条|^\d+\.\s|^\d+、', re.MULTILINE)

    # 章节标题：只匹配真正的章节/小节标题，不匹配编号列表项
    HEADER_PATTERN = re.compile(
        r'^(?:第[一二三四五六七八九十1234567890]+章|第\d+章|'
        r'第[一二三四五六七八九十]+节|第\d+节|'
        r'^[一二三四五六七八九十]+[、\.])',
        re.MULTILINE
    )

    # Markdown 标题
    MARKDOWN_HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

    MAX_EMBEDDING_LENGTH = 2000

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 50,
        table_row_chunk_size: int = 600,
    ):
        """
        初始化切片器

        :param chunk_size: 普通文本切片大小（字符数）
        :param chunk_overlap: 切片重叠（字符数）
        :param min_chunk_size: 最小切片大小
        :param table_row_chunk_size: 表格类切片大小
        """
        self.chunk_size = min(chunk_size, self.MAX_EMBEDDING_LENGTH)
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.table_row_chunk_size = min(table_row_chunk_size, self.MAX_EMBEDDING_LENGTH)

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        切分Document列表，根据 doc_type 选择策略

        对于文本量小于 chunk_size 的小文档，额外插入一个全文档概览切片，
        确保概览类问题（如"有哪些指标""分为几级"）能直接命中完整文档上下文。

        :param documents: 原始Document列表
        :return: 切分后的Document列表
        """
        all_chunks = []
        chunk_index = 0

        for doc in documents:
            doc_type = doc.metadata.get("doc_type", "txt")
            doc_text = doc.page_content.strip()
            doc_len = len(doc_text)

            # 小文档（文本量 < chunk_size）：先插入全文档概览切片
            overview_added = False
            if doc_type != "excel" and doc_len > 0 and doc_len < self.chunk_size:
                overview_meta = doc.metadata.copy()
                overview_meta["chunk_index"] = chunk_index
                overview_meta["chunk_type"] = "overview"
                overview_meta["chunk_id"] = self._generate_chunk_id(
                    overview_meta.get("doc_id", ""), chunk_index
                )
                overview_doc = Document(
                    page_content=f"[文档概览]\n{doc_text}",
                    metadata=overview_meta,
                )
                all_chunks.append(overview_doc)
                chunk_index += 1
                overview_added = True
                logger.debug(f"小文档概览切片已追加: {doc.metadata.get('doc_name', '?')} ({doc_len}字符)")

            try:
                if doc_type == "excel":
                    chunks = self._split_excel_document(doc, chunk_index)
                elif doc_type == "markdown":
                    chunks = self._split_markdown_document(doc, chunk_index)
                else:
                    # pdf / word / txt 统一按文本处理
                    chunks = self._split_text_document(doc, chunk_index)
            except Exception as e:
                logger.warning(f"文档切片失败 [{doc_type}]: {doc.metadata.get('doc_name', 'unknown')}, 错误: {e}")
                chunks = self._fallback_split(doc, chunk_index)

            if chunks:
                all_chunks.extend(chunks)
                chunk_index += len(chunks)

            # 概览切片追加后跳过了 chunk_index 递增，需要重新编号后续切片
            # （已通过 split_document 内的 start_index 参数自然处理）

        logger.info(f"切片完成: {len(documents)}个文档 -> {len(all_chunks)}个切片")
        return all_chunks

    def _split_excel_document(
        self,
        document: Document,
        start_index: int
    ) -> List[Document]:
        """
        Excel 行级记录切片：每行已经是独立 Document，只需增强列上下文
        """
        content = document.page_content.strip()
        if not content or len(content) < self.min_chunk_size:
            return []

        metadata = document.metadata.copy()
        metadata["chunk_index"] = start_index
        metadata["chunk_type"] = "excel_row"
        metadata["chunk_id"] = self._generate_chunk_id(
            metadata.get("doc_id", ""), start_index
        )

        return [Document(page_content=content, metadata=metadata)]

    def _split_markdown_document(
        self,
        document: Document,
        start_index: int
    ) -> List[Document]:
        """
        Markdown 文档切片：按标题层级组织，保留表格
        """
        text = document.page_content
        metadata = document.metadata.copy()

        if not text or not text.strip():
            return []

        # 1. 提取 Markdown 表格
        tables = self._extract_markdown_tables(text)
        non_table_text = self._remove_tables(text, tables)

        # 1.5. 提取 HTML 表格（如 JTG F80 等规范文档中的 <table>）
        html_tables = self._extract_html_tables(non_table_text)
        non_table_text = self._remove_html_tables(non_table_text)

        chunks = []
        chunk_index = start_index

        # 2. 表格按行切片，每个行携带表头和最近标题
        for table in tables:
            table_chunks = self._split_markdown_table(
                table, metadata, chunk_index, non_table_text
            )
            chunks.extend(table_chunks)
            chunk_index += len(table_chunks)

        # 2.5. HTML 表按行切片
        for html_table in html_tables:
            html_chunks = self._split_html_table(
                html_table, metadata, chunk_index, text
            )
            chunks.extend(html_chunks)
            chunk_index += len(html_chunks)

        # 3. 非表格文本按标题分段
        section_chunks = self._split_by_markdown_headers(
            non_table_text, metadata, chunk_index
        )
        chunks.extend(section_chunks)

        return chunks

    def _split_text_document(
        self,
        document: Document,
        start_index: int
    ) -> List[Document]:
        """
        PDF/Word/TXT 通用文本切片：识别表格、标题、段落
        """
        text = document.page_content
        metadata = document.metadata.copy()

        if not text or not text.strip():
            return []

        # 1. 提取表格（Markdown 格式 + 空格对齐 + Word " | " 格式）
        tables = self._extract_all_tables(text)
        non_table_text = self._remove_tables(text, tables)

        # 1.5. 提取 HTML 表格
        html_tables = self._extract_html_tables(non_table_text)
        non_table_text = self._remove_html_tables(non_table_text)

        chunks = []
        chunk_index = start_index

        # 2. 表格按行切片
        for table in tables:
            table_chunks = self._split_text_table(
                table, metadata, chunk_index
            )
            chunks.extend(table_chunks)
            chunk_index += len(table_chunks)

        # 2.5. HTML 表按行切片
        for html_table in html_tables:
            html_chunks = self._split_html_table(
                html_table, metadata, chunk_index, text
            )
            chunks.extend(html_chunks)
            chunk_index += len(html_chunks)

        # 3. 正文按段落和标题切片
        section_chunks = self._split_paragraphs_with_headers(
            non_table_text, metadata, chunk_index
        )
        chunks.extend(section_chunks)

        return chunks

    def _extract_all_tables(self, text: str) -> List[str]:
        """
        提取所有表格：Markdown 表格、Word " | " 行、空格对齐表格
        """
        tables = []

        # 策略 A：Markdown 表格
        md_tables = self._extract_markdown_tables(text)
        tables.extend(md_tables)
        remaining = self._remove_tables(text, md_tables)

        # 策略 B：Word 转换的 " | " 分隔行（至少 2 列，且行首行尾无 |）
        word_tables = self._extract_word_like_tables(remaining)
        tables.extend(word_tables)
        remaining = self._remove_tables(remaining, word_tables)

        # 策略 C：空格对齐的多列表格（PDF 常见）
        space_tables = self._extract_space_aligned_tables(remaining)
        tables.extend(space_tables)

        return tables

    def _extract_markdown_tables(self, text: str) -> List[str]:
        """
        提取 Markdown 表格
        """
        tables = []
        lines = text.split('\n')
        current_table = []
        in_table = False

        for line in lines:
            stripped = line.strip()
            if self.MARKDOWN_TABLE_PATTERN.match(stripped):
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

    def _extract_html_tables(self, text: str) -> List[str]:
        """
        提取 HTML <table>...</table> 块
        """
        return self.HTML_TABLE_PATTERN.findall(text)

    def _remove_html_tables(self, text: str) -> str:
        """
        从文本中移除 HTML 表格块
        """
        return self.HTML_TABLE_PATTERN.sub('', text)

    def _split_html_table(
        self,
        table_html: str,
        metadata: Dict[str, Any],
        start_index: int,
        full_text: str,
        caption: str = "",
    ) -> List[Document]:
        """
        将 HTML 表格按行切片，每行携带表头上下文

        :param table_html: <table>...</table> 内的 HTML
        :param metadata: 文档元数据
        :param start_index: 起始切片索引
        :param full_text: 完整文本（用于查找表格标题）
        :param caption: 表格标题（如果已知）
        :return: 切片列表
        """
        # 解析表头和所有行
        tr_matches = self.HTML_TR_PATTERN.findall(table_html)
        if not tr_matches:
            return []

        all_rows = []
        for tr_html in tr_matches:
            cells = self.HTML_CELL_PATTERN.findall(tr_html)
            clean_cells = [self._strip_html_tags(c).strip() for c in cells]
            clean_cells = [c for c in clean_cells if c]
            if clean_cells:
                all_rows.append(clean_cells)

        if len(all_rows) < 2:
            return []

        # 找到最大行长度作为表头参考
        max_header_len = max(len(r) for r in all_rows)
        header_row = [r for r in all_rows if len(r) >= max_header_len - 1]
        header_cells = header_row[0] if header_row else all_rows[0]
        header_text = " | ".join(header_cells)

        # 查找表格标题
        if not caption:
            caption = self._find_table_caption_for_html(full_text, table_html)

        chunks = []
        for row_cells in all_rows:
            if row_cells == header_cells:
                continue  # 跳过表头行本身
            if len(row_cells) < 2:
                continue  # 跳过太短的行

            kv_parts = []
            for j, cell in enumerate(row_cells):
                if j < len(header_cells):
                    kv_parts.append(f"{header_cells[j]}: {cell}")
                else:
                    kv_parts.append(cell)

            row_text = " | ".join(kv_parts)
            prefix = f"表头: {caption or ''}\n列名: {header_text}\n" if caption or header_text else ""

            chunk_meta = metadata.copy()
            chunk_meta.update({
                "chunk_index": start_index + len(chunks),
                "chunk_type": "table_row",
                "is_table_row": True,
                "table_caption": caption,
                "table_header": header_text,
            })

            # 应用语义标签
            content = prefix + row_text
            tags = self._build_semantic_tags(content, chunk_meta, "table_row")
            if tags:
                content = f"{tags}\n{content}"

            chunks.append(Document(
                page_content=content,
                metadata=chunk_meta,
            ))

        return chunks

    def _find_table_caption_for_html(self, full_text: str, table_html: str) -> str:
        """
        为 HTML 表格查找前置标题
        """
        idx = full_text.find(table_html)
        if idx < 0:
            return ""
        # 查找表格前的文本
        prefix = full_text[max(0, idx - 300):idx]
        lines = prefix.split('\n')
        # 从后往前找"表 X.X.X" 或类似标题
        for line in reversed(lines):
            stripped = line.strip().lstrip('#').strip()
            if re.search(r'表\s*\d+(\.\d+)*', stripped) or '表' in stripped:
                return stripped
        return ""

    @staticmethod
    def _strip_html_tags(html: str) -> str:
        """
        移除 HTML 标签保留文本
        """
        return re.sub(r'<[^>]+>', '', html)

    def _extract_word_like_tables(self, text: str) -> List[str]:
        """
        提取 Word 转换后的 " | " 分隔表格
        条件：连续多行包含 " | "，且每行至少有 2 个分隔
        """
        tables = []
        lines = text.split('\n')
        current_table = []

        for line in lines:
            stripped = line.strip()
            if stripped.count(' | ') >= 2:
                current_table.append(stripped)
            else:
                if len(current_table) >= 3:
                    tables.append('\n'.join(current_table))
                current_table = []

        if len(current_table) >= 3:
            tables.append('\n'.join(current_table))

        return tables

    def _extract_space_aligned_tables(self, text: str) -> List[str]:
        """
        提取 PDF 中空格对齐的表格
        启发式：连续多行具有 2-8 列空格分隔，且列位置对齐
        """
        tables = []
        lines = text.split('\n')
        current_table = []

        for line in lines:
            stripped = line.strip()
            # 过滤纯空行和页眉页脚标记
            if not stripped or stripped.startswith('[第') or len(stripped) < 10:
                if len(current_table) >= 3:
                    tables.append('\n'.join(current_table))
                current_table = []
                continue

            # 检查是否像表格行：包含多个 2+ 空格分隔的段
            parts = [p.strip() for p in re.split(r'\s{2,}', stripped) if p.strip()]
            if 2 <= len(parts) <= 8 and any(p for p in parts):
                current_table.append(stripped)
            else:
                if len(current_table) >= 3:
                    tables.append('\n'.join(current_table))
                current_table = []

        if len(current_table) >= 3:
            tables.append('\n'.join(current_table))

        return tables

    def _split_markdown_table(
        self,
        table_text: str,
        metadata: Dict[str, Any],
        start_index: int,
        full_text: str
    ) -> List[Document]:
        """
        将 Markdown 表格按行切片，每行携带表头
        """
        lines = [l.strip() for l in table_text.split('\n') if l.strip()]
        if len(lines) < 2:
            return []

        # 表头行和分隔符行
        header_line = lines[0]
        header_cells = [c.strip() for c in header_line.strip('|').split('|')]
        header_cells = [c for c in header_cells if c]

        data_lines = []
        for line in lines[1:]:
            stripped_inner = line.replace('|', '').replace('-', '').strip()
            if not stripped_inner or stripped_inner == '':
                continue
            # Markdown 表格分隔符行：仅包含 |、-、: 和空格
            if re.match(r'^[\|\-\:\s]+$', line.strip()):
                continue
            data_lines.append(line)

        if not header_cells or not data_lines:
            return []

        # 尝试找到表格标题
        table_caption = self._find_table_caption(table_text, full_text)
        nearest_header = self._find_nearest_header(full_text, table_text)

        header_text = " | ".join(header_cells)
        chunks = []

        for i, line in enumerate(data_lines):
            cells = [c.strip() for c in line.strip('|').split('|')]
            cells = [c for c in cells if c]
            if not cells:
                continue

            # 生成 "列名: 值" 的键值对文本
            kv_parts = []
            for j, cell in enumerate(cells):
                if j < len(header_cells):
                    kv_parts.append(f"{header_cells[j]}: {cell}")
                else:
                    kv_parts.append(cell)

            content_parts = []
            if table_caption:
                content_parts.append(f"表格：{table_caption}")
            if nearest_header:
                content_parts.append(f"章节：{nearest_header}")
            content_parts.append(f"表头：{header_text}")
            content_parts.append(" | ".join(kv_parts))

            content = "\n".join(content_parts)
            if len(content) > self.MAX_EMBEDDING_LENGTH:
                content = content[:self.MAX_EMBEDDING_LENGTH]

            chunk_metadata = metadata.copy()
            chunk_metadata["chunk_index"] = start_index + i
            chunk_metadata["chunk_type"] = "table_row"
            chunk_metadata["is_table"] = True
            chunk_metadata["table_header"] = header_text
            chunk_metadata["table_caption"] = table_caption
            chunk_metadata["nearest_header"] = nearest_header
            chunk_metadata["chunk_id"] = self._generate_chunk_id(
                metadata.get("doc_id", ""), start_index + i
            )

            # 应用语义标签
            tags = self._build_semantic_tags(content, chunk_metadata, "table_row")
            if tags:
                content = f"{tags}\n{content}"

            chunks.append(Document(page_content=content, metadata=chunk_metadata))

        return chunks

    def _split_text_table(
        self,
        table_text: str,
        metadata: Dict[str, Any],
        start_index: int
    ) -> List[Document]:
        """
        将文本/Word/PDF 表格按行切片
        """
        lines = [l.strip() for l in table_text.split('\n') if l.strip()]
        if len(lines) < 2:
            return []

        # 判断表头：第一行
        header_line = lines[0]
        delimiter = ' | ' if ' | ' in header_line else r'\s{2,}'
        header_cells = [c.strip() for c in re.split(delimiter, header_line) if c.strip()]

        data_lines = lines[1:]
        if not header_cells:
            header_cells = ["项目", "内容"]

        chunks = []
        for i, line in enumerate(data_lines):
            if not line or '---' in line:
                continue
            cells = [c.strip() for c in re.split(delimiter, line) if c.strip()]
            if len(cells) < 1:
                continue

            kv_parts = []
            for j, cell in enumerate(cells):
                if j < len(header_cells):
                    kv_parts.append(f"{header_cells[j]}: {cell}")
                else:
                    kv_parts.append(cell)

            header_text = " | ".join(header_cells)
            content = f"表头：{header_text}\n" + " | ".join(kv_parts)
            if len(content) > self.MAX_EMBEDDING_LENGTH:
                content = content[:self.MAX_EMBEDDING_LENGTH]

            chunk_metadata = metadata.copy()
            chunk_metadata["chunk_index"] = start_index + i
            chunk_metadata["chunk_type"] = "table_row"
            chunk_metadata["is_table"] = True
            chunk_metadata["table_header"] = header_text
            chunk_metadata["chunk_id"] = self._generate_chunk_id(
                metadata.get("doc_id", ""), start_index + i
            )

            # 应用语义标签
            tags = self._build_semantic_tags(content, chunk_metadata, "table_row")
            if tags:
                content = f"{tags}\n{content}"

            chunks.append(Document(page_content=content, metadata=chunk_metadata))

        return chunks

    def _split_by_markdown_headers(
        self,
        text: str,
        metadata: Dict[str, Any],
        start_index: int
    ) -> List[Document]:
        """
        按 Markdown 标题层级切分文本
        """
        lines = text.split('\n')
        chunks = []
        current_header = ""
        current_content = []
        chunk_index = start_index

        def flush_section():
            nonlocal chunks, chunk_index, current_content
            if not current_content:
                return
            content_text = '\n'.join(current_content).strip()
            if len(content_text) < self.min_chunk_size:
                current_content = []
                return

            contents = self._chunk_large_text(
                content_text, current_header, metadata, chunk_index
            )
            chunks.extend(contents)
            chunk_index += len(contents)
            current_content = []

        for line in lines:
            header_match = self.MARKDOWN_HEADER_PATTERN.match(line)
            if header_match:
                flush_section()
                current_header = header_match.group(2).strip()
                current_content.append(f"## {current_header}")
            else:
                current_content.append(line)

        flush_section()
        return chunks

    def _split_paragraphs_with_headers(
        self,
        text: str,
        metadata: Dict[str, Any],
        start_index: int
    ) -> List[Document]:
        """
        通用文本段落切片，保留最近标题/章节上下文。
        对编号列表（如 1. / A. / （一））做特殊处理：把同一条跨行内容合并。
        """
        lines = text.split('\n')
        chunks = []
        current_header = ""
        current_content = []
        chunk_index = start_index
        in_article = False

        def flush_paragraphs():
            nonlocal chunks, chunk_index, current_content, in_article
            if not current_content:
                in_article = False
                return
            content_text = '\n'.join(current_content).strip()

            # 条例项允许更短；普通段落受 min_chunk_size 限制
            is_article = self.ARTICLE_PATTERN.match(content_text.split('\n')[0])
            min_len = 5 if is_article else self.min_chunk_size
            if len(content_text) < min_len:
                current_content = []
                in_article = False
                return

            chunk_type = "article" if is_article else "paragraph"
            contents = self._chunk_large_text(
                content_text, current_header, metadata, chunk_index, chunk_type
            )
            chunks.extend(contents)
            chunk_index += len(contents)
            current_content = []
            in_article = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 检测章节标题
            if self.HEADER_PATTERN.match(stripped) or stripped.endswith('：') or stripped.endswith(':'):
                flush_paragraphs()
                current_header = stripped.rstrip('：:').strip()
                continue

            # 检测条例编号开头
            if self.ARTICLE_PATTERN.match(stripped):
                flush_paragraphs()
                current_content.append(stripped)
                in_article = True
            elif in_article:
                # 继续合并到当前条例项（处理跨行规则）
                current_content.append(stripped)
            else:
                current_content.append(stripped)

        flush_paragraphs()
        return chunks

    def _chunk_large_text(
        self,
        text: str,
        header: str,
        metadata: Dict[str, Any],
        start_index: int,
        chunk_type: str = "paragraph",
    ) -> List[Document]:
        """
        对大段落按句子切分，保留标题上下文
        """
        if len(text) <= self.chunk_size:
            content = f"章节：{header}\n{text}" if header else text
            return [self._create_chunk(content, metadata, start_index, chunk_type)]

        sentences = self._split_sentences(text)
        chunks = []
        current_chunk = header + "\n" if header else ""
        chunk_index = start_index

        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= self.chunk_size:
                current_chunk += sentence
            else:
                if current_chunk.strip():
                    chunks.append(self._create_chunk(
                        current_chunk.strip(), metadata, chunk_index, chunk_type
                    ))
                    chunk_index += 1

                overlap = self._get_overlap_text(current_chunk)
                current_chunk = (overlap + "\n" if overlap else "") + (header + "\n" if header else "") + sentence

        if current_chunk.strip():
            chunks.append(self._create_chunk(
                current_chunk.strip(), metadata, chunk_index, chunk_type
            ))

        return chunks

    def _create_chunk(
        self,
        content: str,
        metadata: Dict[str, Any],
        index: int,
        chunk_type: str
    ) -> Document:
        """
        创建统一切片Document，添加语义标签前缀辅助 Embedding 对齐
        """
        if len(content) > self.MAX_EMBEDDING_LENGTH:
            content = content[:self.MAX_EMBEDDING_LENGTH]

        # 生成语义标签前缀，帮助 Embedding 对齐查询
        semantic_tags = self._build_semantic_tags(content, metadata, chunk_type)
        if semantic_tags:
            content = f"{semantic_tags}\n{content}"

        chunk_metadata = metadata.copy()
        chunk_metadata["chunk_index"] = index
        chunk_metadata["chunk_type"] = chunk_type
        chunk_metadata["chunk_id"] = self._generate_chunk_id(
            metadata.get("doc_id", ""), index
        )
        return Document(page_content=content, metadata=chunk_metadata)

    def _build_semantic_tags(
        self,
        content: str,
        metadata: Dict[str, Any],
        chunk_type: str,
    ) -> str:
        """
        根据切片类型和内容生成语义标签前缀，辅助 Embedding 对齐

        :param content: 切片文本
        :param metadata: 切片元数据
        :param chunk_type: 切片类型
        :return: 标签字符串，如 "[操作流程] [试验步骤] [土工膜]"
        """
        tags = []
        header = metadata.get("nearest_header", "") or ""

        # 表格类标签
        if chunk_type in ("table_row", "excel_row") or metadata.get("is_table"):
            tags.append("表格数据")
            # 检测表格内容类型
            if any(kw in content or kw in header for kw in ["扣分", "分值", "处罚", "罚款"]):
                tags.append("扣分标准")
            if any(kw in content or kw in header for kw in ["压实度", "强度", "厚度", "粒径", "温度"]):
                tags.append("技术标准")
            if any(kw in content or kw in header for kw in ["检测", "试验", "取样", "频率"]):
                tags.append("检测要求")

        # 条例类标签
        if chunk_type == "article":
            tags.append("条例规定")
            if any(kw in content for kw in ["扣分", "分值", "处罚", "罚款"]):
                tags.append("扣分标准")
            if any(kw in content or kw in header for kw in ["要求", "应", "不得", "必须"]):
                tags.append("规范要求")

        # 根据章节标题内容添加语义标签
        combined = content + header
        chapter_keywords = {
            "试验步骤": ["试验步骤", "检测步骤", "操作步骤", "操作规程"],
            "测定方法": ["试验方法", "测定方法", "检测方法", "测定步骤", "标准方法"],
            "操作流程": ["操作流程", "工作流程", "实施流程", "处理流程"],
            "技术标准": ["技术要求", "技术标准", "质量要求", "质量标准", "验收标准", "评定标准"],
            "检测项目": ["检测项目", "检验项目", "检查内容", "检测内容"],
            "分类目录": ["分类", "类型", "种类", "目录", "总则", "概述", "包含"],
            "取样方法": ["取样", "试件制备", "制样"],
            "扣分标准": ["扣分", "处罚标准", "考核标准", "惩戒"],
            "术语定义": ["术语", "定义", "解释", "简称", "缩写"],
        }
        for tag, keywords in chapter_keywords.items():
            if any(kw in combined for kw in keywords):
                tags.append(tag)

        # 检测试验方法名（T编号+法名，如 T0103 烘干法），添加到标签
        method_matches = re.findall(r'(T\d{4})\s+(\S+?法)', combined)
        if method_matches:
            if "测定方法" not in tags:
                tags.append("测定方法")
            for _, method_name in method_matches[:3]:  # 最多取3个方法名
                if method_name not in tags:
                    tags.append(method_name)

        # 段落类：检测是否与步骤/方法相关
        if chunk_type == "paragraph":
            if any(kw in combined for kw in [
                "步骤", "流程", "操作", "方法如下", "按以下", "顺序",
                "首先", "然后", "接着", "最后"
            ]):
                if "操作流程" not in tags:
                    tags.append("操作流程")
                if "试验步骤" not in tags:
                    tags.append("试验步骤")

        return f"[{'] ['.join(tags)}]" if tags else ""

    def _fallback_split(
        self,
        document: Document,
        start_index: int
    ) -> List[Document]:
        """
        异常回退切片：按固定长度切
        """
        text = document.page_content
        metadata = document.metadata.copy()
        chunks = []

        for i in range(0, len(text), self.chunk_size):
            content = text[i:i + self.chunk_size]
            if len(content) < self.min_chunk_size:
                continue
            chunks.append(self._create_chunk(
                content, metadata, start_index + i // self.chunk_size, "fallback"
            ))

        return chunks

    def _find_table_caption(self, table_text: str, full_text: str) -> Optional[str]:
        """
        从表格附近查找表题（如"表1：xxx"）
        """
        index = full_text.find(table_text)
        if index == -1:
            return None

        # 向前查找 200 字符
        before = full_text[max(0, index - 200):index]
        match = re.search(r'表\s*\d+[\.、]?\s*[^\n]{2,50}', before)
        if match:
            return match.group(0).strip()

        return None

    def _find_nearest_header(self, full_text: str, table_text: str) -> Optional[str]:
        """
        查找表格最近的章节标题
        """
        index = full_text.find(table_text)
        if index == -1:
            return None

        before = full_text[:index]
        headers = list(self.MARKDOWN_HEADER_PATTERN.finditer(before))
        if headers:
            last = headers[-1]
            return last.group(2).strip()

        # 通用标题匹配
        lines = before.split('\n')
        for line in reversed(lines[-20:]):
            stripped = line.strip()
            if stripped and (self.HEADER_PATTERN.match(stripped) or stripped.endswith('：')):
                return stripped.rstrip('：:').strip()

        return None

    def _remove_tables(self, text: str, tables: List[str]) -> str:
        """
        从文本中移除已提取的表格
        """
        result = text
        for table in tables:
            result = result.replace(table, '')
        return result

    def _split_sentences(self, text: str) -> List[str]:
        """
        按句子分割文本
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
        """
        if len(text) <= self.chunk_overlap:
            return text

        overlap = text[-self.chunk_overlap:]
        match = re.search(r'[。！？；\n]', overlap)
        if match:
            overlap = overlap[match.end():]

        return overlap

    def _generate_chunk_id(self, doc_id: str, index: int) -> str:
        """
        生成切片ID
        """
        unique_str = f"{doc_id}_{index}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:16]
