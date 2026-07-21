"""
文档加载器模块
将多格式文档（Markdown/PDF/Word/TXT/Excel）转换为LangChain Document
"""
from typing import List, Dict, Any
from pathlib import Path
from loguru import logger
import hashlib
import re

from langchain_core.documents import Document


class TxtLoader:
    """
    纯文本加载器
    将TXT文件转换为LangChain Document
    """

    def __init__(self, file_path: str):
        """
        初始化TXT加载器

        :param file_path: TXT文件路径
        """
        self.file_path = Path(file_path)

    def load(self) -> List[Document]:
        """
        加载TXT文件为Document列表

        :return: Document列表
        """
        try:
            # 尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            text = None
            for enc in encodings:
                try:
                    with open(self.file_path, 'r', encoding=enc) as f:
                        text = f.read()
                    break
                except UnicodeDecodeError:
                    continue

            if text is None:
                logger.error(f"无法解码文件: {self.file_path.name}")
                return []

            if not text.strip():
                return []

            doc_id = hashlib.md5(self.file_path.name.encode()).hexdigest()[:16]
            doc_name = self.file_path.stem

            metadata = {
                "doc_id": doc_id,
                "doc_name": doc_name,
                "doc_type": "txt",
                "source_type": "local",
                "file_path": str(self.file_path),
            }

            document = Document(
                page_content=text,
                metadata=metadata,
            )

            logger.info(f"TXT加载完成: {self.file_path.name}, {len(text)}字符")
            return [document]

        except Exception as e:
            logger.error(f"加载TXT失败: {self.file_path.name}, 错误: {e}")
            return []


class PDFLoader:
    """
    PDF文档加载器
    使用pypdf提取文本内容，并对表格行进行空格对齐格式化
    """

    def __init__(self, file_path: str):
        """
        初始化PDF加载器

        :param file_path: PDF文件路径
        """
        self.file_path = Path(file_path)

    def load(self) -> List[Document]:
        """
        加载PDF文件为Document列表

        优先使用 PyMuPDF (fitz) 提取文本，保留更好的布局和换行；
        不可用时回退到 pypdf。

        :return: Document列表
        """
        try:
            text, total_pages = self._load_with_fitz()
        except Exception as fitz_error:
            logger.warning(f"PyMuPDF提取失败，回退到pypdf: {fitz_error}")
            try:
                text, total_pages = self._load_with_pypdf()
            except Exception as pypdf_error:
                logger.error(f"加载PDF失败: {self.file_path.name}, 错误: {pypdf_error}")
                return []

        if not text.strip():
            logger.warning(f"PDF未提取到有效文本: {self.file_path.name}")
            return []

        doc_id = hashlib.md5(self.file_path.name.encode()).hexdigest()[:16]
        doc_name = self.file_path.stem

        metadata = {
            "doc_id": doc_id,
            "doc_name": doc_name,
            "doc_type": "pdf",
            "source_type": "local",
            "file_path": str(self.file_path),
            "total_pages": total_pages,
        }

        document = Document(
            page_content=text,
            metadata=metadata,
        )

        logger.info(f"PDF加载完成: {self.file_path.name}, {total_pages}页, {len(text)}字符")
        return [document]

    def _load_with_fitz(self) -> tuple:
        """
        使用 PyMuPDF 提取文本

        :return: (文本内容, 总页数)
        """
        import fitz

        doc = fitz.open(str(self.file_path))
        text_parts = []

        for i, page in enumerate(doc):
            page_text = page.get_text()
            if not page_text.strip():
                continue

            # 对可能的表格行进行 Markdown 格式化
            formatted_text = self._format_tables(page_text)
            text_parts.append(f"[第{i+1}页]\n{formatted_text.strip()}")

        text = "\n\n".join(text_parts)
        total_pages = len(doc)
        doc.close()

        return text, total_pages

    def _load_with_pypdf(self) -> tuple:
        """
        使用 pypdf 提取文本（回退方案）

        :return: (文本内容, 总页数)
        """
        from pypdf import PdfReader

        reader = PdfReader(str(self.file_path))
        text_parts = []

        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            if not page_text.strip():
                continue

            formatted_text = self._format_tables(page_text)
            text_parts.append(f"[第{i+1}页]\n{formatted_text.strip()}")

        text = "\n\n".join(text_parts)
        return text, len(reader.pages)

    def _format_tables(self, text: str) -> str:
        """
        将PDF中提取的空格对齐表格转换为 Markdown 表格格式，便于后续切片识别
        """
        lines = text.split('\n')
        result_lines = []
        current_table = []

        def flush_table():
            nonlocal result_lines, current_table
            if len(current_table) >= 3:
                table_lines = self._space_table_to_markdown(current_table)
                result_lines.extend(table_lines)
            elif current_table:
                result_lines.extend(current_table)
            current_table = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                flush_table()
                result_lines.append(line)
                continue

            # 过滤页眉页脚
            if stripped.startswith('[第') and '页]' in stripped:
                result_lines.append(line)
                continue

            parts = [p.strip() for p in re.split(r'\s{2,}', stripped) if p.strip()]
            if 2 <= len(parts) <= 8 and self._looks_like_table_row(parts):
                current_table.append(stripped)
            else:
                flush_table()
                result_lines.append(line)

        flush_table()
        return '\n'.join(result_lines)

    def _looks_like_table_row(self, parts: List[str]) -> bool:
        """
        启发式判断是否为表格行：至少有一个数字或短文本列
        """
        return any(len(p) < 30 or re.search(r'\d', p) for p in parts)

    def _space_table_to_markdown(self, rows: List[str]) -> List[str]:
        """
        将空格对齐的行转换为 Markdown 表格
        """
        parsed_rows = []
        for row in rows:
            cells = [p.strip() for p in re.split(r'\s{2,}', row.strip()) if p.strip()]
            parsed_rows.append(cells)

        if not parsed_rows:
            return rows

        max_cols = max(len(r) for r in parsed_rows)
        md_rows = []
        for cells in parsed_rows:
            padded = cells + [''] * (max_cols - len(cells))
            md_rows.append('| ' + ' | '.join(padded) + ' |')

        # 插入表头分隔符
        if len(md_rows) >= 1:
            separator = '| ' + ' | '.join(['---'] * max_cols) + ' |'
            md_rows.insert(1, separator)

        return md_rows


class WordLoader:
    """
    Word文档加载器（.docx）
    使用python-docx提取文本内容，表格转为 Markdown 格式
    """

    def __init__(self, file_path: str):
        """
        初始化Word加载器

        :param file_path: Word文件路径（.docx）
        """
        self.file_path = Path(file_path)

    def load(self) -> List[Document]:
        """
        加载Word文件为Document列表

        :return: Document列表
        """
        try:
            from docx import Document as DocxDocument

            doc = DocxDocument(str(self.file_path))
            text_parts = []

            # 提取段落文本
            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)

            # 提取表格内容，转为 Markdown 表格
            for table in doc.tables:
                md_table = self._table_to_markdown(table)
                if md_table:
                    text_parts.append(md_table)

            text = "\n\n".join(text_parts)

            if not text.strip():
                logger.warning(f"Word文档未提取到有效文本: {self.file_path.name}")
                return []

            doc_id = hashlib.md5(self.file_path.name.encode()).hexdigest()[:16]
            doc_name = self.file_path.stem

            metadata = {
                "doc_id": doc_id,
                "doc_name": doc_name,
                "doc_type": "word",
                "source_type": "local",
                "file_path": str(self.file_path),
            }

            document = Document(
                page_content=text,
                metadata=metadata,
            )

            logger.info(f"Word加载完成: {self.file_path.name}, {len(text)}字符")
            return [document]

        except Exception as e:
            logger.error(f"加载Word失败: {self.file_path.name}, 错误: {e}")
            return []

    def _table_to_markdown(self, table) -> str:
        """
        将Word表格转换为Markdown表格
        """
        rows = []
        for row in table.rows:
            cells = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
            if any(cells):
                rows.append('| ' + ' | '.join(cells) + ' |')

        if len(rows) < 2:
            return "\n".join(rows)

        # 插入Markdown表头分隔符
        col_count = len(table.rows[0].cells)
        separator = '| ' + ' | '.join(['---'] * col_count) + ' |'
        rows.insert(1, separator)

        return "\n".join(rows)


class MarkdownLoader:
    """
    Markdown文档加载器
    将Markdown文件转换为LangChain Document列表
    """

    def __init__(self, file_path: str):
        """
        初始化Markdown加载器

        :param file_path: Markdown文件路径
        """
        self.file_path = Path(file_path)

    def load(self) -> List[Document]:
        """
        加载Markdown文件为Document列表

        :return: Document列表
        """
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                text = f.read()

            if not text.strip():
                return []

            doc_id = hashlib.md5(self.file_path.name.encode()).hexdigest()[:16]
            doc_name = self.file_path.stem

            metadata = {
                "doc_id": doc_id,
                "doc_name": doc_name,
                "doc_type": "markdown",
                "source_type": "local",
                "file_path": str(self.file_path),
            }

            document = Document(
                page_content=text,
                metadata=metadata,
            )

            logger.info(f"Markdown加载完成: {self.file_path.name}, {len(text)}字符")
            return [document]

        except Exception as e:
            logger.error(f"加载Markdown失败: {self.file_path.name}, 错误: {e}")
            return []


class ExcelLoader:
    """
    Excel文档加载器
    将Excel文件转换为LangChain Document列表
    """

    def __init__(self, file_path: str):
        """
        初始化Excel加载器

        :param file_path: Excel文件路径
        """
        self.file_path = Path(file_path)

    def load(self) -> List[Document]:
        """
        加载Excel文件为Document列表

        :return: Document列表
        """
        try:
            import pandas as pd

            suffix = self.file_path.suffix.lower()
            if suffix == '.xls':
                df = pd.read_excel(self.file_path, engine='xlrd')
            else:
                df = pd.read_excel(self.file_path, engine='openpyxl')

            df.columns = [str(col).strip() if 'Unnamed' not in str(col) else ''
                         for col in df.columns]
            df = df.dropna(how='all').fillna('')

            columns = [str(col).strip() for col in df.columns
                      if col and 'Unnamed' not in str(col)]

            doc_id = hashlib.md5(self.file_path.name.encode()).hexdigest()[:16]
            doc_name = self.file_path.stem
            header_text = " | ".join(columns)

            documents = []
            for idx, row in df.iterrows():
                parts = []
                for col in columns:
                    if col and col in row.index:
                        value = str(row[col]).strip()
                        if value and value != 'nan':
                            parts.append(f"{col}: {value}")

                if not parts:
                    continue

                # 增强行级内容：表格名 + 表头 + 键值对
                content = f"表格：{doc_name}\n表头：{header_text}\n" + " | ".join(parts)

                metadata = {
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "doc_type": "excel",
                    "source_type": "local",
                    "file_path": str(self.file_path),
                    "row_index": int(idx),
                    "table_header": header_text,
                }

                documents.append(Document(
                    page_content=content,
                    metadata=metadata,
                ))

            logger.info(f"Excel加载完成: {self.file_path.name}, {len(documents)}条记录")
            return documents

        except Exception as e:
            logger.error(f"加载Excel失败: {self.file_path.name}, 错误: {e}")
            return []


def load_documents_from_directory(directory: str) -> List[Document]:
    """
    从目录加载所有文档（支持MD/PDF/Word/TXT/Excel）

    :param directory: 目录路径
    :return: Document列表
    """
    dir_path = Path(directory)
    all_documents = []
    loaders = [
        ("*.md", MarkdownLoader),
        ("*.txt", TxtLoader),
        ("*.pdf", PDFLoader),
        ("*.docx", WordLoader),
    ]
    for pattern, loader_cls in loaders:
        for file_path in dir_path.glob(pattern):
            loader = loader_cls(str(file_path))
            docs = loader.load()
            all_documents.extend(docs)

    for excel_file in list(dir_path.glob("*.xls")) + list(dir_path.glob("*.xlsx")):
        loader = ExcelLoader(str(excel_file))
        docs = loader.load()
        all_documents.extend(docs)

    logger.info(f"目录加载完成: {directory}, 共{len(all_documents)}个Document")
    return all_documents
