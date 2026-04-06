"""
查询缓存模块
缓存常见问题的答案，提升响应速度
"""
from typing import Optional, Dict, Any, List
from loguru import logger
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import threading


class QueryCache:
    """
    查询缓存器
    使用内存缓存常见问题的答案
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = 3600,
        cache_file: Optional[str] = None
    ):
        """
        初始化缓存器
        
        :param max_size: 最大缓存数量
        :param ttl_seconds: 缓存过期时间（秒）
        :param cache_file: 缓存文件路径（可选）
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache_file = Path(cache_file) if cache_file else None
        
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        
        if self.cache_file and self.cache_file.exists():
            self._load_from_file()
    
    def _generate_key(self, question: str, use_web_search: bool = False) -> str:
        """
        生成缓存键
        
        :param question: 问题
        :param use_web_search: 是否使用网络检索
        :return: 缓存键
        """
        content = f"{question}:{use_web_search}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def get(
        self,
        question: str,
        use_web_search: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        获取缓存的答案
        
        :param question: 问题
        :param use_web_search: 是否使用网络检索
        :return: 缓存的答案（如果存在且未过期）
        """
        key = self._generate_key(question, use_web_search)
        
        with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            
            if datetime.now() > entry['expires_at']:
                del self._cache[key]
                return None
            
            logger.info(f"缓存命中: {question[:30]}...")
            return entry['data']
    
    def set(
        self,
        question: str,
        data: Dict[str, Any],
        use_web_search: bool = False
    ):
        """
        缓存答案
        
        :param question: 问题
        :param data: 答案数据
        :param use_web_search: 是否使用网络检索
        """
        key = self._generate_key(question, use_web_search)
        
        with self._lock:
            if len(self._cache) >= self.max_size:
                self._evict_oldest()
            
            self._cache[key] = {
                'data': data,
                'question': question,
                'created_at': datetime.now(),
                'expires_at': datetime.now() + timedelta(seconds=self.ttl_seconds)
            }
            
            logger.debug(f"缓存已保存: {question[:30]}...")
    
    def _evict_oldest(self):
        """
        清理最旧的缓存
        """
        if not self._cache:
            return
        
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k]['created_at']
        )
        del self._cache[oldest_key]
    
    def clear(self):
        """
        清空缓存
        """
        with self._lock:
            self._cache.clear()
            logger.info("缓存已清空")
    
    def invalidate(self, question: str, use_web_search: bool = False):
        """
        使指定问题的缓存失效
        
        :param question: 问题
        :param use_web_search: 是否使用网络检索
        """
        key = self._generate_key(question, use_web_search)
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.info(f"缓存已失效: {question[:30]}...")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        :return: 统计信息
        """
        with self._lock:
            return {
                'total_entries': len(self._cache),
                'max_size': self.max_size,
                'ttl_seconds': self.ttl_seconds
            }
    
    def _load_from_file(self):
        """
        从文件加载缓存
        """
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for key, entry in data.items():
                entry['created_at'] = datetime.fromisoformat(entry['created_at'])
                entry['expires_at'] = datetime.fromisoformat(entry['expires_at'])
                
                if datetime.now() < entry['expires_at']:
                    self._cache[key] = entry
            
            logger.info(f"从文件加载缓存: {len(self._cache)}条")
        except Exception as e:
            logger.warning(f"加载缓存文件失败: {e}")
    
    def save_to_file(self):
        """
        保存缓存到文件
        """
        if not self.cache_file:
            return
        
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {}
            for key, entry in self._cache.items():
                data[key] = {
                    'data': entry['data'],
                    'question': entry['question'],
                    'created_at': entry['created_at'].isoformat(),
                    'expires_at': entry['expires_at'].isoformat()
                }
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"缓存已保存到文件: {len(self._cache)}条")
        except Exception as e:
            logger.warning(f"保存缓存文件失败: {e}")


_cache_instance: Optional[QueryCache] = None


def get_query_cache(
    max_size: int = 1000,
    ttl_seconds: int = 3600,
    cache_file: Optional[str] = None
) -> QueryCache:
    """
    获取QueryCache单例
    
    :param max_size: 最大缓存数量
    :param ttl_seconds: 缓存过期时间
    :param cache_file: 缓存文件路径
    :return: QueryCache实例
    """
    global _cache_instance
    
    if _cache_instance is None:
        _cache_instance = QueryCache(
            max_size=max_size,
            ttl_seconds=ttl_seconds,
            cache_file=cache_file
        )
    
    return _cache_instance
