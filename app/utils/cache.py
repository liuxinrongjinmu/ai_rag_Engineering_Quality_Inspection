"""
查询缓存模块
缓存常见问题的答案，提升响应速度
支持Redis后端 + 内存后端降级
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from loguru import logger
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import threading


class CacheBackend(ABC):
    """
    缓存后端抽象基类
    """

    @abstractmethod
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存值

        :param key: 缓存键
        :return: 缓存数据，不存在返回None
        """
        ...

    @abstractmethod
    def set(self, key: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        """
        设置缓存值

        :param key: 缓存键
        :param data: 缓存数据
        :param ttl_seconds: 过期时间(秒)
        """
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """
        删除缓存

        :param key: 缓存键
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """
        清空所有缓存
        """
        ...

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计

        :return: 统计信息
        """
        ...


class MemoryCacheBackend(CacheBackend):
    """
    内存缓存后端
    """

    def __init__(self, max_size: int = 1000):
        """
        初始化内存缓存

        :param max_size: 最大缓存数量
        """
        self.max_size = max_size
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存值

        :param key: 缓存键
        :return: 缓存数据
        """
        with self._lock:
            if key not in self._cache:
                return None

            entry = self._cache[key]

            if datetime.now() > entry['expires_at']:
                del self._cache[key]
                return None

            return entry['data']

    def set(self, key: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        """
        设置缓存值

        :param key: 缓存键
        :param data: 缓存数据
        :param ttl_seconds: 过期时间(秒)
        """
        with self._lock:
            if len(self._cache) >= self.max_size:
                self._evict_oldest()

            self._cache[key] = {
                'data': data,
                'created_at': datetime.now(),
                'expires_at': datetime.now() + timedelta(seconds=ttl_seconds),
            }

    def delete(self, key: str) -> None:
        """
        删除缓存

        :param key: 缓存键
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def clear(self) -> None:
        """
        清空所有缓存
        """
        with self._lock:
            self._cache.clear()
            logger.info("内存缓存已清空")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计

        :return: 统计信息
        """
        with self._lock:
            return {
                'backend': 'memory',
                'total_entries': len(self._cache),
                'max_size': self.max_size,
            }

    def _evict_oldest(self) -> None:
        """
        清理最旧的缓存
        """
        if not self._cache:
            return

        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k]['created_at'],
        )
        del self._cache[oldest_key]


class RedisCacheBackend(CacheBackend):
    """
    Redis缓存后端
    """

    def __init__(self, redis_url: str):
        """
        初始化Redis缓存

        :param redis_url: Redis连接URL
        """
        import redis
        self.redis = redis.Redis.from_url(
            redis_url,
            decode_responses=False,
        )
        self.redis.ping()
        logger.info("Redis缓存后端初始化成功")

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存值

        :param key: 缓存键
        :return: 缓存数据
        """
        try:
            data = self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Redis读取失败: {e}")
        return None

    def set(self, key: str, data: Dict[str, Any], ttl_seconds: int) -> None:
        """
        设置缓存值

        :param key: 缓存键
        :param data: 缓存数据
        :param ttl_seconds: 过期时间(秒)
        """
        try:
            self.redis.setex(
                key,
                ttl_seconds,
                json.dumps(data, ensure_ascii=False),
            )
        except Exception as e:
            logger.warning(f"Redis写入失败: {e}")

    def delete(self, key: str) -> None:
        """
        删除缓存

        :param key: 缓存键
        """
        try:
            self.redis.delete(key)
        except Exception as e:
            logger.warning(f"Redis删除失败: {e}")

    def clear(self) -> None:
        """
        清空所有缓存
        """
        try:
            self.redis.flushdb()
            logger.info("Redis缓存已清空")
        except Exception as e:
            logger.warning(f"Redis清空失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计

        :return: 统计信息
        """
        try:
            return {
                'backend': 'redis',
                'total_entries': self.redis.dbsize(),
            }
        except Exception:
            return {'backend': 'redis', 'total_entries': 0}


class QueryCache:
    """
    查询缓存器
    自动选择Redis或内存后端
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = 3600,
        redis_url: Optional[str] = None,
        cache_file: Optional[str] = None,
    ):
        """
        初始化缓存器

        :param max_size: 最大缓存数量（内存后端）
        :param ttl_seconds: 缓存过期时间（秒）
        :param redis_url: Redis连接URL（可选，不配则用内存）
        :param cache_file: 缓存文件路径（仅内存后端支持）
        """
        self.ttl_seconds = ttl_seconds

        if redis_url:
            try:
                self.backend: CacheBackend = RedisCacheBackend(redis_url)
                logger.info(f"缓存后端: Redis")
            except Exception as e:
                logger.warning(f"Redis连接失败，降级为内存缓存: {e}")
                self.backend = MemoryCacheBackend(max_size)
        else:
            self.backend = MemoryCacheBackend(max_size)
            logger.info("缓存后端: 内存")

    def _generate_key(self, question: str, use_web_search: bool = False) -> str:
        """
        生成缓存键（含知识库版本，重建后自动失效）

        :param question: 问题
        :param use_web_search: 是否使用网络检索
        :return: 缓存键
        """
        kb_gen = _get_kb_generation()
        content = f"{question}:{use_web_search}:kb_gen{kb_gen}"
        return f"rag:cache:{hashlib.md5(content.encode('utf-8')).hexdigest()}"

    def get(
        self,
        question: str,
        use_web_search: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        获取缓存的答案

        :param question: 问题
        :param use_web_search: 是否使用网络检索
        :return: 缓存的答案（如果存在）
        """
        key = self._generate_key(question, use_web_search)
        result = self.backend.get(key)
        if result:
            logger.info(f"缓存命中: {question[:30]}...")
        return result

    def set(
        self,
        question: str,
        data: Dict[str, Any],
        use_web_search: bool = False,
    ) -> None:
        """
        缓存答案

        :param question: 问题
        :param data: 答案数据
        :param use_web_search: 是否使用网络检索
        """
        key = self._generate_key(question, use_web_search)
        self.backend.set(key, data, self.ttl_seconds)
        logger.debug(f"缓存已保存: {question[:30]}...")

    def clear(self) -> None:
        """
        清空缓存
        """
        self.backend.clear()

    def invalidate(self, question: str, use_web_search: bool = False) -> None:
        """
        使指定问题的缓存失效

        :param question: 问题
        :param use_web_search: 是否使用网络检索
        """
        key = self._generate_key(question, use_web_search)
        self.backend.delete(key)
        logger.info(f"缓存已失效: {question[:30]}...")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        :return: 统计信息
        """
        stats = self.backend.get_stats()
        stats['ttl_seconds'] = self.ttl_seconds
        return stats


_cache_instance: Optional[QueryCache] = None


def get_query_cache(
    max_size: int = 1000,
    ttl_seconds: int = 3600,
    redis_url: Optional[str] = None,
    cache_file: Optional[str] = None,
) -> QueryCache:
    """
    获取QueryCache单例

    :param max_size: 最大缓存数量
    :param ttl_seconds: 缓存过期时间
    :param redis_url: Redis URL（可选）
    :param cache_file: 缓存文件路径
    :return: QueryCache实例
    """
    global _cache_instance

    if _cache_instance is None:
        if redis_url is None:
            from app.config import get_settings
            settings = get_settings()
            redis_url = getattr(settings, 'REDIS_URL', None)

        _cache_instance = QueryCache(
            max_size=max_size,
            ttl_seconds=ttl_seconds,
            redis_url=redis_url,
            cache_file=cache_file,
        )

    return _cache_instance


# ======== 知识库版本号（缓存自动失效机制）========
# 重建知识库后版本号递增，所有缓存 key 自动变化，旧缓存自然失效
# 无需跨进程通信，所有进程读取同一个文件

import os as _os

_KB_GEN_FILE = None


def _get_kb_gen_file() -> str:
    """获取知识库版本文件路径"""
    global _KB_GEN_FILE
    if _KB_GEN_FILE is None:
        from app.config import get_settings as _get_settings
        _settings = _get_settings()
        chroma_dir = _settings.CHROMA_PERSIST_DIR
        _KB_GEN_FILE = str(Path(chroma_dir) / "kb_generation.txt")
    return _KB_GEN_FILE


def _get_kb_generation() -> int:
    """
    读取当前知识库版本号（所有进程共享，通过文件读取）

    :return: 版本号，不存在则返回 0
    """
    try:
        gen_file = _get_kb_gen_file()
        if _os.path.exists(gen_file):
            with open(gen_file, 'r') as f:
                return int(f.read().strip())
    except Exception:
        pass
    return 0


def bump_kb_generation() -> int:
    """
    递增知识库版本号（重建KB后调用，使所有缓存自动失效）

    :return: 新版本号
    """
    gen_file = _get_kb_gen_file()
    current = _get_kb_generation()
    new_gen = current + 1
    _os.makedirs(_os.path.dirname(gen_file), exist_ok=True)
    with open(gen_file, 'w') as f:
        f.write(str(new_gen))
    logger.info(f"知识库版本号已更新: {current} -> {new_gen}（所有查询缓存自动失效）")
    return new_gen
