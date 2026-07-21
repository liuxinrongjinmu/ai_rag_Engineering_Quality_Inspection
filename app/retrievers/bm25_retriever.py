"""
BM25关键词检索器
基于langchain-community的BM25Retriever
"""
from typing import List, Optional, TYPE_CHECKING
from loguru import logger
import pickle
import os
import jieba

from langchain_core.documents import Document

if TYPE_CHECKING:
    from langchain_community.retrievers import BM25Retriever

_bm25_retriever_instance: Optional["BM25Retriever"] = None


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
        # 考核/规章类词汇
        "扣分", "罚款", "投诉", "客户投诉", "考核标准",
        "服务质量", "工作质量", "业务培训", "宣传活动",
    ]
    for word in domain_words:
        jieba.add_word(word)


def _tokenize_func(text: str) -> List[str]:
    """
    中文分词函数（含Bigram增强：生成2-gram捕捉复合词如"试验步骤"）

    :param text: 输入文本
    :return: 分词结果（含unigram和bigram）
    """
    import re
    tokens = list(jieba.cut(text))
    stop_words = set(['的', '了', '和', '是', '在', '有', '对', '为', '与', '及'])
    tokens = [t.strip() for t in tokens if t.strip() and t.strip() not in stop_words]
    tokens = [t for t in tokens if len(t) > 1 or re.match(r'[A-Za-z0-9]', t)]

    # Bigram增强：将相邻token拼接为2-gram，捕捉领域复合词
    # 如 ["试验", "步骤"] → 增加 bigram "试验步骤"，提升BM25 IDF权重
    bigrams = []
    for i in range(len(tokens) - 1):
        bigram = tokens[i] + tokens[i + 1]
        if len(bigram) >= 3 and len(bigram) <= 10:
            bigrams.append(bigram)

    tokens.extend(bigrams)
    return tokens


def get_bm25_retriever() -> Optional["BM25Retriever"]:
    """
    获取BM25Retriever单例

    :return: BM25Retriever实例
    """
    global _bm25_retriever_instance
    return _bm25_retriever_instance


def build_bm25_retriever(documents: List[Document]) -> "BM25Retriever":
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


def save_bm25_retriever(retriever: "BM25Retriever", path: str):
    """
    保存BM25检索器（原子写入：先写.tmp，成功后重命名）

    :param retriever: BM25Retriever实例
    :param path: 保存路径
    """
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)

    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, 'wb') as f:
            pickle.dump(retriever, f)
        os.replace(tmp_path, path)  # 原子重命名（跨平台安全）
        logger.info(f"BM25检索器已保存: {path}")
    except Exception as e:
        logger.error(f"BM25检索器保存失败: {e}")
        # 清理临时文件
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        raise


def load_bm25_retriever(path: str) -> Optional["BM25Retriever"]:
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
