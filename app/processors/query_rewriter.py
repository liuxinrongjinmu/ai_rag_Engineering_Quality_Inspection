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
    
    # 口语化表达到规范术语的映射（公路工程质检 + 通用规章/考核文档）
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

        # 规范术语（只做同义词映射，不注入数据值）
        "压实度": "压实度",
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
        "含水率试验": "含水率试验",
        "抗压强度试验": "单轴抗压强度试验",
        "单轴抗压": "单轴抗压强度",
        "软化系数": "软化系数",

        # 试验相关技术术语（只映射同义词）
        "试件": "试件",
        "标准试件": "标准试件",
        "高径比": "高径比",
        "冻融": "冻融试验",
        "烘干": "烘干",

        # 集料术语
        "粗集料": "粗集料",
        "细集料": "细集料",
        "填料": "填料",

        # 无机结合料术语（纯同义词，不注入数据值）
        "无机结合料": "无机结合料稳定材料",
        "稳定材料": "无机结合料稳定材料",
        "细粒材料": "细粒材料",
        "中粒材料": "中粒材料",
        "粗粒材料": "粗粒材料",
        "水泥剂量": "水泥剂量 EDTA滴定",

        # 通用规章/考核文档（表格问答常用）
        "扣几分": "扣分",
        "扣多少分": "扣分",
        "罚多少": "处罚",
        "罚款": "罚款金额",
        "投诉": "投诉",
        "被投诉": "投诉",
        "考核": "考核标准",
        "处罚": "处罚标准",
        "标准": "标准",
        "规定": "规定",
        "要求": "要求",
        "流程": "流程",
        "步骤": "试验步骤 检测步骤 方法",
        "试验步骤": "试验步骤 检测步骤 方法",
        "检测步骤": "检测步骤 试验步骤 方法",
        "方法": "方法",
        "怎么办": "处理办法",
        "如何做": "操作方法",
        # 泛化"影响"类问题映射到扣分/处罚
        "有什么影响": "扣分",
        "有啥影响": "扣分",
        "什么后果": "处罚",
        "怎么样": "处理办法",
        "处罚措施": "处罚",
        "怎么处理": "处理办法",
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

        # 2. 规则替换无变化时，尝试LLM重写（当前禁用，LLM重写稳定性不足）
        # if rewritten == original_query and self.api_key:
        #     llm_result = self._llm_rewrite(original_query)
        #     if llm_result != original_query:
        #         rewritten = llm_result

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
        
        # 应用术语映射（按长度降序替换，避免短词污染长词）
        # 使用边界匹配防止部分替换：re.sub(r'\b' + colloquial + r'\b', formal, result)
        sorted_mappings = sorted(self.TERM_MAPPINGS.items(), key=lambda x: -len(x[0]))
        for colloquial, formal in sorted_mappings:
            if colloquial in result:
                if formal not in result:
                    result = result.replace(colloquial, formal, 1)
        
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
        
        # 规范化问句（公路工程 + 通用规章/考核）
        patterns = [
            (r"(.+?)是多少[？?]?$", r"\1是多少"),
            (r"(.+?)怎么[做搞测检][？?]?$", r"\1方法"),
            (r"(.+?)有哪些[？?]?$", r"\1检测项目"),
            (r"(.+?)包括哪些[？?]?$", r"\1检测项目"),
            (r"(.+?)扣几分[？?]?$", r"\1扣分"),
            (r"(.+?)扣多少分[？?]?$", r"\1扣分"),
            (r"(.+?)罚多少[款钱]?[？?]?$", r"\1罚款"),
            # 泛化"影响/后果"类 → 扣分/处罚
            (r"(.+?)有什么影响[？?]?$", r"\1扣分 处罚"),
            (r"(.+?)有啥影响[？?]?$", r"\1扣分 处罚"),
            (r"(.+?)什么后果[？?]?$", r"\1处罚"),
            (r"(.+?)会怎么样[？?]?$", r"\1处理办法"),
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
            
            prompt = f"""将以下口语问题改写为规范术语关键词查询。禁止输出任何解释、前缀、换行，只输出改写后的关键词。

原始问题：{query}

改写（只输出关键词）："""

            response = Generation.call(
                model="qwen-turbo",
                prompt=prompt,
                max_tokens=50,
                temperature=0.0,
            )

            if response.status_code == 200:
                result = response.output.text.strip()
                # 过滤LLM常见废话前缀
                for bad_prefix in ["规范查询：", "专业术语：", "改写：", "查询：", "关键词：", "输出："]:
                    if result.startswith(bad_prefix):
                        result = result[len(bad_prefix):].strip()
                if result and len(result) <= len(query) * 3 and result != query:
                    return result
            
        except Exception as e:
            logger.warning(f"LLM重写失败: {e}")
        
        return query
    
    # 意图分类模式
    INTENT_PATTERNS = {
        "numeric": r'多少|几[个处次]|扣[多少几分]|罚[多少款钱]|不低于|不超过|不小于|不大于|大于|小于|等于|标准值|规定值',
        "procedure": r'步骤|流程|怎么做|如何[做检测]|方法|操作|规程|顺序|过程',
        "overview": r'包含哪些|有哪些|哪些项目|种类|分类|类型|分为|分为几|有几[种个]|分别是什么|都[有些]什么|等级|级别|几级|严重等级|有几级',
        "impact": r'影响|后果|怎么样|有啥|有什么|会怎样|处罚|罚款|处理',
        "causal": r'为什么|原因|为何|怎么造成|怎么会',
        "comparison": r'区别|不同|对比|哪个|哪种|还是|或者',
    }

    def _classify_intent(self, query: str) -> List[str]:
        """
        对查询进行意图分类，返回匹配的意图标签列表

        :param query: 查询文本
        :return: 意图标签列表（可能命中多个意图）
        """
        intents = []
        for intent, pattern in self.INTENT_PATTERNS.items():
            if re.search(pattern, query):
                intents.append(intent)
        if not intents:
            intents.append("general")
        return intents

    def expand_query(self, query: str) -> List[str]:
        """
        扩展查询（基于意图分类生成多个相关查询，提高召回率）

        :param query: 原始查询
        :return: 扩展后的查询列表
        """
        queries = [query]

        # 添加重写版本
        rewritten = self.rewrite(query)
        if rewritten != query:
            queries.append(rewritten)

        # 意图分类，按意图生成定向变体
        intents = self._classify_intent(query)
        logger.debug(f"查询意图分类: '{query[:40]}...' → {intents}")

        for intent in intents:
            intent_variants = self._generate_intent_variants(query, intent)
            queries.extend(intent_variants)

        # 针对"不低于/不超过"类比较问法，生成纯关键词变体
        comparison_variants = self._generate_comparison_variants(query)
        queries.extend(comparison_variants)

        # 添加关键词组合
        keywords = self._extract_keywords(query)
        if keywords:
            for keyword in keywords:
                if keyword not in query and keyword not in rewritten:
                    queries.append(f"{query} {keyword}")

        # 去重并限制数量
        unique_queries = []
        seen = set()
        for q in queries:
            normalized = q.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_queries.append(normalized)

        return unique_queries[:6]

    def _generate_intent_variants(self, query: str, intent: str) -> List[str]:
        """
        根据意图分类生成定向查询变体

        :param query: 原始查询
        :param intent: 意图标签
        :return: 变体列表
        """
        variants = []

        if intent == "numeric":
            # 数值类：生成"标准值"、"规定值"、"技术要求"变体
            if "标准" not in query:
                variants.append(query + " 标准")
            if "规定" not in query:
                variants.append(query + " 规定")
            if "数值" not in query:
                variants.append(query + " 规定值")
            # 扣分类变体
            if "扣" in query:
                variants.append(query.replace("扣几分", "扣分标准").replace("扣多少分", "扣分标准"))
                if "投诉" in query:
                    variants.append("投诉 扣分标准")
                    variants.append("客户投诉 扣分")
            # 比较类数值（不低于/不超过）
            if re.search(r'不低于|不超过|不小于|不大于', query):
                variants.append(query.replace("不低于", "最低").replace("不超过", "最高"))

        elif intent == "procedure":
            # 区分"方法名称"（如：用什么方法测定）和"操作步骤"（如：怎么做、步骤）
            is_method_name_query = bool(re.search(r'什么方法|哪种方法|哪[个些]方法|方法[是叫]*什么', query))

            if is_method_name_query:
                # 用户在问"用什么方法测"→ 生成"测定方法 试验方法"变体，不展开步骤
                variants.append(query + " 测定方法 试验方法")
                variants.append(query.replace("什么方法", "方法").replace("哪种方法", "方法").strip() + " 烘干法 酒精燃烧法")
                variants.append(query.replace("用什么方法", "").replace("什么方法", "").strip() + " 测定方法")
            else:
                # 操作步骤/流程类
                variants.append(query + " 试验步骤 检测步骤")
                if "步骤" in query:
                    variants.append(query.replace("步骤", "试验步骤"))
                    variants.append(query.replace("步骤", "检测步骤"))
                    variants.append(query.replace("步骤", "操作规程"))
                # 提取主体，生成关键词组合
                match = re.search(r'(.+?)(的|怎么|如何)?步骤', query)
                if match:
                    subject = match.group(1).strip()
                    if subject and len(subject) > 1:
                        variants.append(f"{subject} 试验步骤")
                        variants.append(f"{subject} 操作规程")
                if "方法" in query and not is_method_name_query:
                    variants.append(query.replace("方法", "试验步骤"))
                    variants.append(query.replace("方法", "操作规程"))
                if "流程" in query:
                    variants.append(query.replace("流程", "步骤 操作规程"))
                if "怎么" in query or "如何" in query:
                    variants.append(query.replace("怎么", "如何").replace("如何", "怎么"))
                    vars_text = re.sub(r'^(.*?)(怎么|如何)(.*)', r'\1\2\3 规定 操作规程', query)
                    variants.append(vars_text)

        elif intent == "impact":
            # 影响/后果类：展开为扣分/处罚/后果关键词
            variants.append(query + " 扣分 处罚")
            if "投诉" in query:
                variants.append("投诉 扣分标准 处罚措施")
            if "影响" in query:
                variants.append(query.replace("影响", "后果").replace("有什么", "").strip())
                variants.append(query + " 扣分标准")

        elif intent == "overview":
            # 概述/分类类：抽取主体生成目录/概览/分类查询
            # 去除问句词，提取主体关键词
            subject = re.sub(r'包含哪些|有哪些|哪些|项目|种类|分类|类型|分为|分别是什么|都[有些]什么|[?？]', '', query).strip()
            if subject:
                variants.append(f"{subject} 目录 章节")
                variants.append(f"{subject} 分类")
                variants.append(f"{subject} 包含")
            # 追加"检测项目"、"试验项目"等扩展
            if "包含" in query or "有哪些" in query or "哪些" in query:
                variants.append(query.replace("包含哪些", "").replace("有哪些", "").replace("哪些", "").strip() + " 检测项目 分类")
                variants.append(query.replace("哪些项目", "").strip() + " 试验项目 分类")
            # 等级/级别分类类：明确检索等级词条
            if "等级" in query or "级别" in query or "几级" in query:
                # 提取主体词（如"塔吊报警严重程度"），生成更直接的检索变体
                subject = re.sub(r'分为|有几|几级|等级|级别|包含哪些|有哪些|哪些|项目|种类|分类|类型|分别是什么|都[有些]什么|[?？]', '', query).strip()
                if subject:
                    variants.append(f"{subject} 等级 级别 分为")
                    variants.append(f"{subject} 严重等级 处理方案")

        elif intent == "causal":
            # 原因类：生成"原因分析"、"影响因素"变体
            variants.append(query.replace("为什么", "").strip() + " 原因分析")
            variants.append(query.replace("为什么", "").strip() + " 影响因素")

        elif intent == "comparison":
            # 对比类：提取对比对象，生成分别查询
            variants.append(query.replace("区别", "").replace("不同", "").strip() + " 对比")

        return variants

    def _generate_table_variants(self, query: str) -> List[str]:
        """
        针对表格类问题生成查询变体
        """
        variants = []

        # 扣分/分值类
        if re.search(r'扣[多少几分]|罚[多少款钱]', query):
            variants.append(query.replace("扣几分", "扣分标准").replace("扣多少分", "扣分标准"))
            variants.append(re.sub(r'^(.*?)(扣几分|扣多少分|罚多少).*', r'\1扣分标准', query))
            # 针对"被投诉一次扣几分"类问题，生成"投诉 扣分"组合
            if "投诉" in query:
                variants.append("投诉 扣分标准")
                variants.append("客户投诉 扣分")

        # 泛化"影响/后果"类 → 展开为扣分/处罚/后果关键词
        if re.search(r'影响|后果|怎么样|有啥|有什么', query):
            if "投诉" in query:
                variants.append("投诉 扣分 处罚")
                variants.append("投诉 扣分标准")
            else:
                variants.append(query + " 扣分 处罚")
                variants.append(query + " 标准")

        # 数量/数值类
        if "多少" in query or "几" in query:
            variants.append(query.replace("多少", "标准").replace("几", "标准"))

        # 方法/流程/步骤类
        if "怎么" in query or "如何" in query:
            variants.append(query.replace("怎么", "如何").replace("如何", "怎么"))
            variants.append(re.sub(r'^(.*?)(怎么|如何)(.*)', r'\1\2\3 规定', query))

        # 步骤类问题：把"步骤"展开为"试验步骤/检测步骤/方法"组合，提升召回
        if "步骤" in query:
            variants.append(query.replace("步骤", "试验步骤"))
            variants.append(query.replace("步骤", "检测步骤"))
            variants.append(query.replace("步骤", "方法"))
            # 提取"XX的步骤"主体，生成"XX 试验步骤"等关键词组合
            match = re.search(r'(.+?)(的|怎么|如何)?步骤', query)
            if match:
                subject = match.group(1).strip()
                if subject and len(subject) > 1:
                    variants.append(f"{subject} 试验步骤")
                    variants.append(f"{subject} 检测步骤")
                    variants.append(f"{subject} 方法")

        return variants

    def _generate_comparison_variants(self, query: str) -> List[str]:
        """
        针对"不低于/不超过/不小于/不大于"类比较问法，
        生成纯关键词变体（剔除比较词和功能词），提升向量/BF25匹配

        例如：'上路床的压实度要求不低于多少？'
           → '上路床 压实度'（纯名词，匹配表头和数据表行）
        """
        variants = []

        # 检测比较类问法
        comp_pattern = r'(不低于|不超过|不小于|不大于|大于|小于|等于|多少|要求|规定)'
        if not re.search(comp_pattern, query):
            return variants

        # 提取中文名词（2字以上词组）
        nouns = re.findall(r'[\u4e00-\u9fa5]{2,}', query)

        # 过滤功能词和比较词
        stop_func = {
            '不低于', '不超过', '不小于', '不大于', '大于', '小于', '等于',
            '多少', '几处', '几次', '几个', '要求', '规定', '标准',
            '和', '的', '了', '是', '在', '有', '对', '为', '与', '及', '或',
            '请问', '帮我', '查一下', '一次', '每次', '一个',
        }
        clean_keywords = [n for n in nouns if n not in stop_func]

        if clean_keywords:
            # 纯关键词变体（空格分隔，适合BM25分词）
            variants.append(' '.join(clean_keywords))

            # 加入"数值"提示词
            variants.append(' '.join(clean_keywords) + ' 规定值 数值')

        return variants

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
