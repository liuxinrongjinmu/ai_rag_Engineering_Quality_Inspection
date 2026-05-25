"""
文档加载器模块
将Markdown和Excel文件转换为LangChain Document
"""
from typing import List, Dict, Any
from pathlib import Path
from loguru import logger
import hashlib

from langchain_core.documents import Document


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

            documents = []
            for idx, row in df.iterrows():
                parts = []
                for col in columns:
                    if col and col in row.index:
                        value = str(row[col]).strip()
                        if value and value != 'nan':
                            parts.append(f"{col}: {value}")

                content = "; ".join(parts)
                if not content.strip():
                    continue

                metadata = {
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "doc_type": "excel",
                    "source_type": "local",
                    "file_path": str(self.file_path),
                    "row_index": int(idx),
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
    从目录加载所有文档

    :param directory: 目录路径
    :return: Document列表
    """
    dir_path = Path(directory)
    all_documents = []

    for md_file in dir_path.glob("*.md"):
        loader = MarkdownLoader(str(md_file))
        docs = loader.load()
        all_documents.extend(docs)

    for excel_file in list(dir_path.glob("*.xls")) + list(dir_path.glob("*.xlsx")):
        loader = ExcelLoader(str(excel_file))
        docs = loader.load()
        all_documents.extend(docs)

    logger.info(f"目录加载完成: {directory}, 共{len(all_documents)}个Document")
    return all_documents
