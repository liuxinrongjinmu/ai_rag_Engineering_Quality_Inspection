"""
Excel解析器
使用pandas解析Excel文件，转换为结构化数据
"""
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger
import hashlib


class ExcelParser:
    """
    Excel文档解析器
    支持xls和xlsx格式
    """
    
    def __init__(self, file_path: str):
        """
        初始化Excel解析器
        
        :param file_path: Excel文件路径
        """
        self.file_path = Path(file_path)
        self.df: Optional[pd.DataFrame] = None
        
    def load(self) -> bool:
        """
        加载Excel文件
        
        :return: 是否成功加载
        """
        try:
            suffix = self.file_path.suffix.lower()
            if suffix == '.xls':
                self.df = pd.read_excel(self.file_path, engine='xlrd')
            else:
                self.df = pd.read_excel(self.file_path, engine='openpyxl')
            
            logger.info(f"成功加载Excel: {self.file_path.name}, 共{len(self.df)}行")
            return True
        except Exception as e:
            logger.error(f"加载Excel失败: {self.file_path.name}, 错误: {e}")
            return False
    
    def get_doc_id(self) -> str:
        """
        生成文档唯一ID
        
        :return: 文档ID
        """
        return hashlib.md5(self.file_path.name.encode()).hexdigest()[:16]
    
    def get_doc_name(self) -> str:
        """
        获取文档名称（去除扩展名）
        
        :return: 文档名称
        """
        return self.file_path.stem
    
    def get_columns(self) -> List[str]:
        """
        获取列名列表
        
        :return: 列名列表
        """
        if self.df is None:
            return []
        
        columns = []
        for col in self.df.columns:
            if 'Unnamed' not in str(col):
                columns.append(str(col).strip())
        
        return columns
    
    def clean_dataframe(self) -> pd.DataFrame:
        """
        清理数据框
        
        :return: 清理后的数据框
        """
        if self.df is None:
            return pd.DataFrame()
        
        df_clean = self.df.copy()
        
        df_clean.columns = [str(col).strip() if 'Unnamed' not in str(col) else '' 
                           for col in df_clean.columns]
        
        df_clean = df_clean.dropna(how='all')
        
        df_clean = df_clean.fillna('')
        
        return df_clean
    
    def row_to_text(self, row: pd.Series, columns: List[str]) -> str:
        """
        将一行数据转换为描述性文本
        
        :param row: 数据行
        :param columns: 列名列表
        :return: 描述性文本
        """
        parts = []
        for col in columns:
            if col and col in row.index:
                value = str(row[col]).strip()
                if value and value != 'nan':
                    parts.append(f"{col}: {value}")
        
        return "; ".join(parts)
    
    def extract_records(self) -> List[Dict[str, Any]]:
        """
        提取所有记录
        
        :return: 记录列表
        """
        if self.df is None:
            return []
        
        df_clean = self.clean_dataframe()
        columns = self.get_columns()
        
        records = []
        for idx, row in df_clean.iterrows():
            text = self.row_to_text(row, columns)
            if text.strip():
                records.append({
                    "row_index": int(idx),
                    "content": text,
                    "raw_data": row.to_dict()
                })
        
        logger.info(f"提取记录完成: {self.file_path.name}, 有效记录: {len(records)}")
        return records
    
    def detect_header_rows(self) -> int:
        """
        检测表头行数
        
        :return: 表头行数
        """
        if self.df is None:
            return 0
        
        header_rows = 0
        for idx, row in self.df.head(5).iterrows():
            if row.isna().all():
                header_rows += 1
            else:
                break
        
        return header_rows
    
    def parse(self) -> Dict[str, Any]:
        """
        完整解析Excel文件
        
        :return: 解析结果
        """
        if not self.load():
            return {}
        
        try:
            records = self.extract_records()
            result = {
                "doc_id": self.get_doc_id(),
                "doc_name": self.get_doc_name(),
                "doc_type": "excel",
                "file_path": str(self.file_path),
                "total_rows": len(records),
                "columns": self.get_columns(),
                "records": records
            }
            return result
        except Exception as e:
            logger.error(f"解析Excel失败: {self.file_path.name}, 错误: {e}")
            return {}


def parse_excel(file_path: str) -> Dict[str, Any]:
    """
    解析Excel文件的便捷函数
    
    :param file_path: Excel文件路径
    :return: 解析结果
    """
    parser = ExcelParser(file_path)
    return parser.parse()
