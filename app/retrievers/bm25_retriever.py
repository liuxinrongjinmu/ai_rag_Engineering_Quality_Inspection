"""
BM25关键词检索器
基于langchain-community的BM25Retriever
"""
from typing import List, Optional
from loguru import logger
import pickle
import os
import jieba

from langchain_core.documents import Document


_bm25_retriever_instance: Optional[object] = None


def _init_jieba():
    """
    初始化jieba分词并加载专业词典
    """
    domain_words = [
        "压实度", "含水率", "抗压强度", "抗折强度", "坍落度",
        "粉煤灰", "钢绞线", "锚具", "集料", "沥青",
        "路基", "路面", "桥梁", "隧道", "桩基",
        "检测频率", "取样方法", "检测项目",
        "块体密度", "击实试验", "CBR试验", "液限塑限",
        "JTG", "GB", "规范", "标准", "规程",
    ]
    for word in domain_words:
        jieba.add_word(word)


def _tokenize_func(text: str) -> List[str]:
    """
    中文分词函数

    :param text: 输入文本
    :return: 分词结果
    """
    import re
    tokens = list(jieba.cut(text))
    stop_words = set(['的', '了', '和', '是', '在', '有', '对', '为', '与', '及'])
    tokens = [t.strip() for t in tokens if t.strip() and t.strip() not in stop_words]
    tokens = [t for t in tokens if len(t) > 1 or re.match(r'[A-Za-z0-9]', t)]
    return tokens


def get_bm25_retriever() -> object:
    """
    获取BM25Retriever单例

    :return: BM25Retriever实例
    """
    global _bm25_retriever_instance
    return _bm25_retriever_instance


def build_bm25_retriever(documents: List[Document]) -> object:
    """
    构建BM25检索器

    :param documents: Document列表
    :return: BM25Retriever实例
    """
    from langchain_community.retrievers import BM25Retriever

    _init_jieba()

    global _bm25_retriever_instance
    _bm25_retriever_instance = BM25Retriever.from_documents(
        documents,
        preprocess_func=_tokenize_func,
    )
    logger.info(f"BM25检索器构建完成: {len(documents)}个文档")

    return _bm25_retriever_instance


def save_bm25_retriever(retriever: object, path: str):
    """
    保存BM25检索器

    :param retriever: BM25Retriever实例
    :param path: 保存路径
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump(retriever, f)
    logger.info(f"BM25检索器已保存: {path}")


def load_bm25_retriever(path: str) -> Optional[object]:
    """
    加载BM25检索器

    :param path: 索引路径
    :return: BM25Retriever实例
    """
    global _bm25_retriever_instance

    if not os.path.exists(path):
        logger.warning(f"BM25索引文件不存在: {path}")
        return None

    try:
        with open(path, 'rb') as f:
            _bm25_retriever_instance = pickle.load(f)
        logger.info(f"BM25检索器已加载: {path}")
        return _bm25_retriever_instance
    except Exception as e:
        logger.error(f"BM25检索器加载失败: {e}")
        return None
