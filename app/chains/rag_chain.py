"""
RAG Chain模块
使用LCEL构建RAG问答链
"""
from typing import List, Optional, Generator, Dict, Any, TYPE_CHECKING
from loguru import logger

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableParallel

if TYPE_CHECKING:
    from langchain_core.runnables import Runnable

_rag_chain_instance: Optional["Runnable"] = None
_stream_chain_instance: Optional["Runnable"] = None


def format_docs(docs: List[Document]) -> str:
    """
    格式化文档列表为上下文字符串，包含文档名帮助LLM识别来源

    :param docs: Document列表
    :return: 格式化后的上下文
    """
    parts = []
    for i, doc in enumerate(docs):
        doc_name = doc.metadata.get("doc_name", "") or ""
        # 提取文档简称（取标准号如 JTG 3431-2024）
        short_name = doc_name[:60] if doc_name else f"资料{i+1}"
        content = f"【文档{i+1}: {short_name}】\n{doc.page_content}\n"
        parts.append(content)

    return "\n" + "=" * 50 + "\n".join(parts)


def get_rag_chain():
    """
    获取RAG Chain单例

    :return: RAG Chain实例
    """
    global _rag_chain_instance

    if _rag_chain_instance is None:
        from app.infrastructure.llm import get_llm
        from app.chains.prompts import RAG_PROMPT

        llm = get_llm()

        _rag_chain_instance = (
            {
                "context": lambda x: format_docs(x["docs"]),
                "question": RunnablePassthrough(),
            }
            | RAG_PROMPT
            | llm
            | StrOutputParser()
        )
        logger.info("RAG Chain初始化成功")

    return _rag_chain_instance


def get_stream_chain():
    """
    获取流式RAG Chain单例

    :return: 流式RAG Chain实例
    """
    global _stream_chain_instance

    if _stream_chain_instance is None:
        from app.infrastructure.llm import get_llm
        from app.chains.prompts import RAG_PROMPT

        llm = get_llm()

        _stream_chain_instance = (
            {
                "context": lambda x: format_docs(x["docs"]),
                "question": RunnablePassthrough(),
            }
            | RAG_PROMPT
            | llm
            | StrOutputParser()
        )
        logger.info("流式RAG Chain初始化成功")

    return _stream_chain_instance


def invoke_rag(question: str, docs: List[Document]) -> str:
    """
    同步调用RAG Chain

    :param question: 用户问题
    :param docs: 检索到的文档
    :return: 生成的答案
    """
    chain = get_rag_chain()
    result = chain.invoke({"docs": docs, "question": question})
    return result


def stream_rag(question: str, docs: List[Document]) -> Generator[str, None, None]:
    """
    流式调用RAG Chain

    :param question: 用户问题
    :param docs: 检索到的文档
    :yield: 生成的文本片段
    """
    chain = get_stream_chain()
    for chunk in chain.stream({"docs": docs, "question": question}):
        yield chunk
