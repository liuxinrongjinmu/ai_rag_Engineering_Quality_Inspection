"""
Markdown解析器
解析Markdown文档，提取文本内容
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger
import re
import hashlib


class MarkdownParser:
    """
    Markdown文档解析器
    支持Markdown文本提取
    """
    
    def __init__(self, file_path: str):
        """
        初始化Markdown解析器
        
        :param file_path: Markdown文件路径
        """
        self.file_path = Path(file_path)
    
    def get_doc_id(self) -> str:
        """
        生成文档唯一ID
        
        :return: 文档ID
        """
        return hashlib.md5(self.file_path.name.encode()).hexdigest()[:16]
    
    def get_doc_name(self) -> str:
        """
        获取文档名称（去除扩展名）
        
        :return: 文档名称
        """
        return self.file_path.stem
    
    def extract_text(self) -> str:
        """
        提取Markdown文本
        
        :return: 文本内容
        """
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            return self._clean_text(text)
        except Exception as e:
            logger.error(f"读取Markdown失败: {self.file_path.name}, 错误: {e}")
            return ""
    
    def _clean_text(self, text: str) -> str:
        """
        清理文本
        
        :param text: 原始文本
        :return: 清理后的文本
        """
        # 移除Markdown格式标记
        text = re.sub(r'#.*?\n', '\n', text)  # 移除标题
        text = re.sub(r'\*\*|__', '', text)   # 移除加粗
        text = re.sub(r'\*|_', '', text)      # 移除斜体
        text = re.sub(r'\[.*?\]\(.*?\)', '', text)  # 移除链接
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)  # 移除代码块
        text = re.sub(r'\s+', ' ', text)      # 合并空白
        text = text.strip()
        return text
    
    def parse(self) -> Dict[str, Any]:
        """
        完整解析Markdown文档
        
        :return: 解析结果，包含文档信息和内容
        """
        try:
            text = self.extract_text()
            
            if not text:
                logger.warning(f"Markdown文件为空: {self.file_path.name}")
                return {}
            
            # 简单分页处理（每1000字符一页）
            pages = []
            page_size = 1000
            for i, start in enumerate(range(0, len(text), page_size)):
                page_content = text[start:start + page_size]
                if page_content.strip():
                    pages.append({
                        "page": i + 1,
                        "content": page_content
                    })
            
            result = {
                "doc_id": self.get_doc_id(),
                "doc_name": self.get_doc_name(),
                "doc_type": "markdown",
                "file_path": str(self.file_path),
                "total_pages": len(pages),
                "pages": pages,
                "tables": [],  # Markdown表格暂不处理
                "structure": []  # 结构暂不提取
            }
            
            logger.info(f"Markdown解析完成: {self.file_path.name}, 生成{len(pages)}页")
            return result
            
        except Exception as e:
            logger.error(f"Markdown解析失败: {self.file_path.name}, 错误: {e}")
            return {}


def parse_markdown(file_path: str) -> Dict[str, Any]:
    """
    解析Markdown文件的便捷函数
    
    :param file_path: Markdown文件路径
    :return: 解析结果
    """
    parser = MarkdownParser(file_path)
    return parser.parse()
