"""
查询重写模块
将用户口语化查询重写为规范术语
"""
from typing import Optional, List, Dict, Any
from loguru import logger
import re


class QueryRewriter:
    """
    查询重写器
    将口语化查询转换为规范术语
    """
    
    # 口语化表达到规范术语的映射
    TERM_MAPPINGS = {
        # 检测项目
        "怎么检": "检测方法",
        "怎么测": "检测方法",
        "怎么取样": "取样方法",
        "取样方法": "取样方法",
        "检测频率": "检测频率",
        "检测周期": "检测频率",
        "多久检一次": "检测频率",
        "检测项目": "检测项目",
        "检什么": "检测项目",
        "有哪些检测": "检测项目",
        
        # 规范术语
        "压实度": "压实度",
        "压实": "压实度",
        "含水率": "含水率",
        "含水量": "含水率",
        "强度": "强度",
        "抗压强度": "抗压强度",
        "抗折强度": "抗折强度",
        "坍落度": "坍落度",
        "塌落度": "坍落度",
        
        # 材料名称
        "粉煤灰": "粉煤灰",
        "水泥": "水泥",
        "混凝土": "混凝土",
        "钢筋": "钢筋",
        "钢绞线": "钢绞线",
        "锚具": "锚具",
        "集料": "集料",
        "碎石": "粗集料",
        "砂": "细集料",
        "沥青": "沥青",
        
        # 工程部位
        "路基": "路基",
        "路面": "路面",
        "桥梁": "桥梁",
        "隧道": "隧道",
        "地基": "地基",
        "桩基": "桩基",
        
        # 试验名称
        "块体密度": "块体密度试验",
        "密度试验": "密度试验",
        "击实试验": "击实试验",
        "CBR": "CBR试验",
        "cbr": "CBR试验",
        "液限塑限": "液限塑限试验",
        "颗粒分析": "颗粒分析试验",
    }
    
    # 规范文档关键词
    STANDARD_KEYWORDS = [
        "JTG", "GB", "DB", "JT/T", "规范", "标准", "规程",
        "公路工程", "质量检验", "试验检测", "检测频率"
    ]
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化查询重写器
        
        :param api_key: API Key（可选，用于LLM重写）
        """
        self.api_key = api_key
    
    def rewrite(self, query: str) -> str:
        """
        重写查询
        
        :param query: 原始查询
        :return: 重写后的查询
        """
        if not query or not query.strip():
            return query
        
        original_query = query.strip()
        
        # 1. 规则替换
        rewritten = self._rule_based_rewrite(original_query)
        
        # 2. 如果有API Key，使用LLM增强重写
        if self.api_key and rewritten == original_query:
            rewritten = self._llm_rewrite(original_query)
        
        if rewritten != original_query:
            logger.info(f"查询重写: '{original_query}' -> '{rewritten}'")
        
        return rewritten
    
    def _rule_based_rewrite(self, query: str) -> str:
        """
        基于规则的重写
        
        :param query: 原始查询
        :return: 重写后的查询
        """
        result = query
        
        # 应用术语映射
        for colloquial, formal in self.TERM_MAPPINGS.items():
            if colloquial in result:
                # 不替换已经包含规范术语的部分
                if formal not in result:
                    result = result.replace(colloquial, formal)
        
        # 处理常见句式
        result = self._normalize_sentence(result)
        
        return result
    
    def _normalize_sentence(self, query: str) -> str:
        """
        规范化句子
        
        :param query: 原始查询
        :return: 规范化后的查询
        """
        result = query
        
        # 移除口语化修饰词
        filler_words = ["请问", "我想知道", "帮我查一下", "查一下", "告诉我"]
        for word in filler_words:
            result = result.replace(word, "")
        
        # 规范化问句
        patterns = [
            (r"(.+?)是多少[？?]?$", r"\1检测频率"),
            (r"(.+?)怎么[做搞测检][？?]?$", r"\1检测方法"),
            (r"(.+?)有哪些[？?]?$", r"\1检测项目"),
            (r"(.+?)包括哪些[？?]?$", r"\1检测项目"),
        ]
        
        for pattern, replacement in patterns:
            match = re.match(pattern, result)
            if match:
                result = re.sub(pattern, replacement, result)
                break
        
        return result.strip()
    
    def _llm_rewrite(self, query: str) -> str:
        """
        使用LLM重写查询
        
        :param query: 原始查询
        :return: 重写后的查询
        """
        if not self.api_key:
            return query
        
        try:
            import dashscope
            from dashscope import Generation
            
            dashscope.api_key = self.api_key
            
            prompt = f"""请将以下公路工程质量检测相关的口语化问题转换为规范的专业术语查询。
要求：
1. 保持原意不变
2. 使用规范的工程术语
3. 简洁明了

原始问题：{query}

规范查询："""
            
            response = Generation.call(
                model="qwen-turbo",
                prompt=prompt,
                max_tokens=100,
                temperature=0.1
            )
            
            if response.status_code == 200:
                result = response.output.text.strip()
                if result and len(result) < len(query) * 2:
                    return result
            
        except Exception as e:
            logger.warning(f"LLM重写失败: {e}")
        
        return query
    
    def expand_query(self, query: str) -> List[str]:
        """
        扩展查询（生成多个相关查询）
        
        :param query: 原始查询
        :return: 扩展后的查询列表
        """
        queries = [query]
        
        # 添加重写版本
        rewritten = self.rewrite(query)
        if rewritten != query:
            queries.append(rewritten)
        
        # 添加关键词组合
        keywords = self._extract_keywords(query)
        if keywords:
            for keyword in keywords:
                if keyword not in query:
                    queries.append(f"{query} {keyword}")
        
        return list(set(queries))
    
    def _extract_keywords(self, query: str) -> List[str]:
        """
        提取关键词
        
        :param query: 查询文本
        :return: 关键词列表
        """
        keywords = []
        
        for keyword in self.STANDARD_KEYWORDS:
            if keyword in query:
                keywords.append(keyword)
        
        return keywords


_query_rewriter_instance: Optional[QueryRewriter] = None


def get_query_rewriter(api_key: Optional[str] = None) -> QueryRewriter:
    """
    获取QueryRewriter单例
    
    :param api_key: API Key
    :return: QueryRewriter实例
    """
    global _query_rewriter_instance
    
    if _query_rewriter_instance is None:
        _query_rewriter_instance = QueryRewriter(api_key)
    
    return _query_rewriter_instance
