"""
LLM工厂模块
使用ChatTongyi创建LLM实例
"""
from typing import Optional
from loguru import logger

from app.config import get_settings


_llm_instance: Optional[object] = None


def get_llm() -> object:
    """
    获取ChatTongyi LLM单例

    :return: ChatTongyi实例
    """
    global _llm_instance

    if _llm_instance is None:
        from langchain_community.chat_models import ChatTongyi

        settings = get_settings()
        _llm_instance = ChatTongyi(
            model=settings.LLM_MODEL,
            dashscope_api_key=settings.DASHSCOPE_API_KEY,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            streaming=True,
        )
        logger.info(f"ChatTongyi LLM初始化成功: model={settings.LLM_MODEL}")

    return _llm_instance
