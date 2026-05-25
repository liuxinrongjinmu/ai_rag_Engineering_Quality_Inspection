"""
RAG Chain模块
使用LCEL构建RAG问答链
"""
from typing import List, Optional, Generator, Dict, Any
from loguru import logger

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableParallel


_rag_chain_instance: Optional[object] = None
_stream_chain_instance: Optional[object] = None


def format_docs(docs: List[Document]) -> str:
    """
    格式化文档列表为上下文字符串

    :param docs: Document列表
    :return: 格式化后的上下文
    """
    parts = []
    for i, doc in enumerate(docs):
        source_info = _format_source_info(doc)
        content = f"【参考资料{i+1}】\n来源: {source_info}\n内容:\n{doc.page_content}\n"
        parts.append(content)

    return "\n" + "=" * 50 + "\n".join(parts)


def _format_source_info(doc: Document) -> str:
    """
    格式化来源信息

    :param doc: Document
    :return: 来源信息字符串
    """
    metadata = doc.metadata

    if metadata.get("source_type") == "web":
        return f"网络来源: {metadata.get('doc_name', '')} ({metadata.get('url', '')})"

    parts = [metadata.get("doc_name", "")]
    if metadata.get("page"):
        parts.append(f"第{metadata['page']}页")
    if metadata.get("section"):
        parts.append(f"第{metadata['section']}节")

    return " - ".join([p for p in parts if p])


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
