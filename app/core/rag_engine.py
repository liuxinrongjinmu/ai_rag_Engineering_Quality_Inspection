"""
RAG引擎
结合检索和生成，实现问答功能
"""
from typing import List, Dict, Any, Optional
from loguru import logger
import time

from app.config import get_settings
from app.models.document import SearchResult, SourceType
from app.models.response import SourceInfo


class RAGEngine:
    """
    RAG引擎
    使用Qwen (通义千问) 进行答案生成
    """
    
    SYSTEM_PROMPT = """你是一位资深的公路工程质量检测专家，拥有丰富的工程实践经验和深厚的专业知识。你的职责是基于提供的规范文档和资料，准确、专业地回答用户关于工程质量检测的问题。

【回答原则】
1. **准确性优先**：必须严格基于提供的参考资料回答，不得编造或臆测
2. **完整提取**：如果参考资料中有表格、列表等结构化内容，请完整提取并呈现
3. **标注来源**：引用具体规范时，标注文档名称、页码、章节等来源信息
4. **直接回答**：不要说"参考资料中没有"、"未找到"等否定性词语，而是直接提取已有信息
5. **表格呈现**：对于检测项目、代码、频率等内容，优先以表格形式呈现

【回答格式】
- 先给出直接答案
- 然后列出具体内容（表格或列表）
- 最后标注来源依据

【特别注意】
- 如果参考资料中有"表4"、"表5"等表格内容，请完整提取表格中的所有行和列
- 不要因为表格内容较长就说"未完整展示"或"部分内容"
- 对于检测项目代码、检测频率等关键信息，必须完整列出"""

    def __init__(self, api_key: str, model: str = "qwen-plus"):
        """
        初始化RAG引擎
        
        :param api_key: DashScope API Key
        :param model: 模型名称
        """
        self.api_key = api_key
        self.model = model
        self._client = None
    
    def initialize(self) -> bool:
        """
        初始化LLM客户端
        
        :return: 是否成功
        """
        try:
            import dashscope
            dashscope.api_key = self.api_key
            self._client = dashscope
            logger.info(f"RAG引擎初始化成功: model={self.model}")
            return True
        except Exception as e:
            logger.error(f"RAG引擎初始化失败: {e}")
            return False
    
    def build_context(
        self,
        results: List[SearchResult],
        max_context_length: int = 6000
    ) -> str:
        """
        构建上下文
        
        :param results: 检索结果
        :param max_context_length: 最大上下文长度
        :return: 上下文字符串
        """
        context_parts = []
        current_length = 0
        
        for i, result in enumerate(results):
            source_info = self._format_source_info(result)
            content = f"【参考资料{i+1}】\n来源: {source_info}\n内容:\n{result.chunk.content}\n"
            
            if current_length + len(content) > max_context_length:
                break
            
            context_parts.append(content)
            current_length += len(content)
        
        return "\n" + "="*50 + "\n".join(context_parts)
    
    def _format_source_info(self, result: SearchResult) -> str:
        """
        格式化来源信息
        
        :param result: 检索结果
        :return: 来源信息字符串
        """
        chunk = result.chunk
        
        if chunk.source_type == SourceType.WEB:
            return f"网络来源: {chunk.doc_name} ({result.source_url})"
        
        parts = [chunk.doc_name]
        
        if chunk.page:
            parts.append(f"第{chunk.page}页")
        
        if chunk.section:
            parts.append(f"第{chunk.section}节")
        
        return " - ".join(parts)
    
    def generate(
        self,
        query: str,
        results: List[SearchResult]
    ) -> Dict[str, Any]:
        """
        生成答案
        
        :param query: 用户问题
        :param results: 检索结果
        :return: 生成结果
        """
        if not self._client:
            if not self.initialize():
                return {
                    "answer": "抱歉，系统暂时无法生成答案，请稍后重试。",
                    "success": False
                }
        
        context = self.build_context(results)
        
        if not context:
            return {
                "answer": "抱歉，没有找到相关的参考资料来回答您的问题。",
                "success": False
            }
        
        prompt = f"""请基于以下参考资料回答用户问题。

{context}

用户问题：{query}

【回答要求】
1. 直接从参考资料中提取相关信息，完整回答问题
2. 如果资料中有表格，请完整呈现表格内容（包括所有行和列）
3. 不要说"参考资料中没有"或"未找到"，而是提取已有信息
4. 标注具体来源（文档名称、页码等）

请开始回答："""
        
        try:
            from dashscope import Generation
            
            response = Generation.call(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                result_format='message',
                max_tokens=2000,
                temperature=0.1
            )
            
            if response.status_code == 200:
                answer = response.output.choices[0].message.content
                return {
                    "answer": answer,
                    "success": True
                }
            else:
                logger.error(f"LLM调用失败: {response.code} - {response.message}")
                return {
                    "answer": f"抱歉，生成答案时出现错误: {response.message}",
                    "success": False
                }
                
        except Exception as e:
            logger.error(f"生成答案失败: {e}")
            return {
                "answer": "抱歉，生成答案时出现错误，请稍后重试。",
                "success": False
            }
    
    def evaluate_answer_quality(
        self,
        query: str,
        answer: str,
        sources: List[SearchResult]
    ) -> Dict[str, Any]:
        """
        使用LLM评估答案质量（内部使用，不返回给用户）
        
        :param query: 用户问题
        :param answer: 生成的答案
        :param sources: 来源列表
        :return: 评估结果
        """
        if not self._client:
            return {"quality": "unknown", "issues": []}
        
        prompt = f"""请评估以下答案的质量：

【用户问题】
{query}

【生成的答案】
{answer}

【参考资料数量】
{len(sources)}个来源

请从以下维度评估答案质量（每项0-10分）：
1. 准确性：答案是否准确反映了参考资料的内容
2. 完整性：答案是否完整回答了用户的问题
3. 可信度：答案是否有明确的来源支撑

请以JSON格式返回评估结果：
{{
    "accuracy": <分数>,
    "completeness": <分数>,
    "credibility": <分数>,
    "issues": ["问题1", "问题2"],
    "suggestion": "改进建议"
}}"""
        
        try:
            from dashscope import Generation
            
            response = Generation.call(
                model="qwen-turbo",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                result_format='message',
                max_tokens=500,
                temperature=0.3
            )
            
            if response.status_code == 200:
                eval_text = response.output.choices[0].message.content
                logger.info(f"答案质量评估: {eval_text[:200]}")
                return {"evaluated": True, "raw": eval_text}
            
        except Exception as e:
            logger.warning(f"答案质量评估失败: {e}")
        
        return {"quality": "unknown", "issues": []}
    
    def extract_sources(
        self,
        results: List[SearchResult]
    ) -> List[SourceInfo]:
        """
        提取来源信息
        
        :param results: 检索结果
        :return: 来源信息列表
        """
        sources = []
        
        for result in results:
            chunk = result.chunk
            
            source = SourceInfo(
                doc_id=chunk.doc_id,
                doc_name=chunk.doc_name,
                page=chunk.page,
                section=chunk.section,
                content=chunk.content[:500] + "..." if len(chunk.content) > 500 else chunk.content,
                source_type=chunk.source_type,
                url=result.source_url if chunk.source_type == SourceType.WEB else None
            )
            sources.append(source)
        
        return sources


_rag_engine_instance: Optional[RAGEngine] = None


def get_rag_engine() -> RAGEngine:
    """
    获取RAGEngine单例
    
    :return: RAGEngine实例
    """
    global _rag_engine_instance
    
    if _rag_engine_instance is None:
        settings = get_settings()
        _rag_engine_instance = RAGEngine(
            api_key=settings.DASHSCOPE_API_KEY
        )
        _rag_engine_instance.initialize()
    
    return _rag_engine_instance
