"""
RAG 系统全量评估脚本 v4 — 扩大测试覆盖面（100+题）
修复BM25初始化问题，覆盖14份文档，多种查询类型
"""
import sys
import asyncio
import re
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.orchestrator import get_orchestrator


@dataclass
class TestCase:
    question: str
    expected_keywords: List[str]
    expected_doc: str
    category: str  # 事实型/推理型/列举型/模糊查询/多关键词/跨文档/数值抽取
    doc_source: str
    tags: List[str] = field(default_factory=list)


# ============================================================
# 100+ 测试用例集
# ============================================================
TEST_CASES = [
    # ═══════════════════════════════════════════════════════
    # JTG F80-1-2017 质量检验评定标准 (8题)
    # ═══════════════════════════════════════════════════════
    TestCase("公路工程质量检验评定中，关键项目的合格率应不低于多少？",
             ["95%", "百分之九十五"], "JTG F80", "事实型", "JTG F80-1-2017",
             tags=["数值型"]),
    TestCase("分项工程质量评定用合格率法代替了原来的什么评定方法？",
             ["合格率法", "综合评分", "综合评分法"], "JTG F80", "事实型", "JTG F80-1-2017",
             tags=["对比型"]),
    TestCase("一般项目的合格率要求不低于多少？",
             ["80%", "百分之八十"], "JTG F80", "事实型", "JTG F80-1-2017",
             tags=["数值型"]),
    TestCase("公路工程质量评定中，实测项目合格率不满足要求怎么处理？",
             ["返工", "处理", "不合格"], "JTG F80", "推理型", "JTG F80-1-2017",
             tags=["推理"]),
    TestCase("混凝土强度不够标准咋办？",
             ["不合格", "处理", "返工", "评定"], "JTG F80", "模糊查询", "JTG F80-1-2017",
             tags=["口语化"]),
    # 新增3题
    TestCase("分项工程质量评定的基本要求是什么？",
             ["基本要求", "实测项目", "外观鉴定", "质量保证资料"], "JTG F80", "列举型", "JTG F80-1-2017",
             tags=["新增", "结构"]),
    TestCase("机电工程关键项目的合格率要求是多少？",
             ["100%", "百分之百"], "JTG F80", "事实型", "JTG F80-1-2017",
             tags=["新增", "数值型"]),
    TestCase("公路工程单位工程、分部工程、分项工程怎么划分？",
             ["单位工程", "分部工程", "分项工程"], "JTG F80", "列举型", "JTG F80-1-2017",
             tags=["新增", "结构"]),

    # ═══════════════════════════════════════════════════════
    # 常用45项公路试验检测项目 (15题)
    # ═══════════════════════════════════════════════════════
    TestCase("土方路基压实度施工自检每200m测几处？",
             ["4", "四处", "4处"], "常用45项", "事实型", "常用45项",
             tags=["数值型", "压实度"]),
    TestCase("水泥进场一批最多多少吨？",
             ["200", "500"], "常用45项", "事实型", "常用45项",
             tags=["数值型", "水泥"]),
    TestCase("钢筋原材取样每批不超过多少吨？",
             ["60", "六十"], "常用45项", "事实型", "常用45项",
             tags=["数值型", "钢筋"]),
    TestCase("细集料有哪些检测项目？",
             ["筛分", "含泥量", "泥块含量", "砂当量", "颗粒组成", "密度"],
             "常用45项|集料", "列举型", "常用45项+JTG 3432",
             tags=["列举型", "概览"]),
    TestCase("水泥剂量施工自检多久抽检一次？",
             ["2小时", "两小时"], "常用45项", "事实型", "常用45项",
             tags=["数值型", "水泥剂量"]),
    TestCase("路基压实度每层要测几个点？频率多少？",
             ["4", "4处", "200m"], "常用45项", "多关键词", "常用45项",
             tags=["多关键词", "压实度"]),
    TestCase("路基压实度检测频率是多少？",
             ["4处", "200m", "每200m"], "常用45项", "多关键词", "常用45项",
             tags=["多关键词"]),
    TestCase("土方路基压实度施工自检每200m测几个地方？",
             ["4处", "四处", "4"], "常用45项", "事实型", "常用45项",
             tags=["口语化"]),
    TestCase("进场水泥一批最多能拉多少吨？",
             ["200", "500"], "常用45项", "事实型", "常用45项",
             tags=["口语化"]),
    TestCase("水泥的检测项目有哪些？",
             ["凝结时间", "安定性", "强度", "细度"], "常用45项", "列举型", "常用45项",
             tags=["列举型"]),
    # 新增5题
    TestCase("钢筋焊接接头拉伸试验取样频率是多少？",
             ["300个", "300"], "常用45项", "事实型", "常用45项",
             tags=["新增", "数值型"]),
    TestCase("沥青原材取样每批多少吨？",
             ["60", "六十"], "常用45项", "事实型", "常用45项",
             tags=["新增", "数值型"]),
    TestCase("路基填料最小强度CBR值要求是多少？",
             ["CBR", "填料", "强度"], "常用45项", "事实型", "常用45项",
             tags=["新增", "数值型"]),
    TestCase("细集料含水率每天最少测几次？",
             ["2次", "4次", "2", "4"], "常用45项", "事实型", "常用45项",
             tags=["新增", "数值型"]),
    TestCase("水泥稳定碎石基层钻芯取样频率？",
             ["钻芯", "频率", "每200m"], "常用45项", "事实型", "常用45项",
             tags=["新增", "数值型"]),

    # ═══════════════════════════════════════════════════════
    # JTG 3431-2024 岩石试验规程 (7题)
    # ═══════════════════════════════════════════════════════
    TestCase("岩石单轴抗压强度标准试件的直径是多少？",
             ["50mm", "50", "高径比", "2"], "JTG 3431", "事实型", "JTG 3431-2024",
             tags=["数值型"]),
    TestCase("岩石软化系数是怎么计算的？",
             ["饱和", "干燥", "抗压强度"], "JTG 3431", "推理型", "JTG 3431-2024",
             tags=["推理型"]),
    TestCase("含水率试验每组需要几个试件？",
             ["5", "五个", "5个"], "JTG 3431", "事实型", "JTG 3431-2024",
             tags=["数值型"]),
    # 新增4题
    TestCase("岩石点荷载试验用什么形状的试件？",
             ["不规则", "圆柱", "方块"], "JTG 3431", "事实型", "JTG 3431-2024",
             tags=["新增", "方法型"]),
    TestCase("岩石抗冻性试验冻融循环多少次？",
             ["25", "25次", "冻融"], "JTG 3431", "事实型", "JTG 3431-2024",
             tags=["新增", "数值型"]),
    TestCase("岩石密度试验有哪些方法？",
             ["量积", "水中称量", "蜡封"], "JTG 3431", "列举型", "JTG 3431-2024",
             tags=["新增", "方法型"]),
    TestCase("岩石的吸水率和饱和吸水率有什么区别？",
             ["吸水率", "饱和", "真空", "煮沸"], "JTG 3431", "推理型", "JTG 3431-2024",
             tags=["新增", "对比型"]),

    # ═══════════════════════════════════════════════════════
    # JTG 3432-2024 集料试验规程 (10题)
    # ═══════════════════════════════════════════════════════
    TestCase("沥青混合料中粗集料和细集料的分界粒径是多少？",
             ["2.36mm", "2.36"], "JTG 3432", "事实型", "JTG 3432-2024",
             tags=["数值型"]),
    TestCase("水泥混凝土中细集料粒径应小于多少？",
             ["4.75mm", "4.75"], "JTG 3432", "事实型", "JTG 3432-2024",
             tags=["数值型"]),
    TestCase("细集料砂当量试验是用来评价什么的？",
             ["含泥量", "黏土", "杂质", "洁净"], "JTG 3432", "推理型", "JTG 3432-2024",
             tags=["推理型"]),
    TestCase("集料的那些检测有啥？",
             ["筛分", "含泥量", "压碎值", "针片状"], "JTG 3432|常用45项", "模糊查询", "JTG 3432-2024+常用45项",
             tags=["口语化"]),
    # 新增6题
    TestCase("粗集料针片状颗粒含量用什么方法测？",
             ["规准仪", "游标卡尺"], "JTG 3432", "事实型", "JTG 3432-2024",
             tags=["新增", "方法型"]),
    TestCase("集料的表观密度和毛体积密度有什么区别？",
             ["表观", "毛体积", "开口孔", "闭口孔"], "JTG 3432", "推理型", "JTG 3432-2024",
             tags=["新增", "对比型"]),
    TestCase("粗集料压碎值试验的试样粒径范围是多少？",
             ["9.5", "13.2", "mm"], "JTG 3432", "事实型", "JTG 3432-2024",
             tags=["新增", "数值型"]),
    TestCase("细集料亚甲蓝试验MBV值用来评价什么？",
             ["含泥量", "石粉", "亚甲蓝", "MBV"], "JTG 3432", "推理型", "JTG 3432-2024",
             tags=["新增", "推理型"]),
    TestCase("沥青混凝土用粗集料的磨光值试验有什么意义？",
             ["磨光", "抗滑", "安全"], "JTG 3432", "推理型", "JTG 3432-2024",
             tags=["新增", "推理型"]),
    TestCase("粗集料坚固性试验用什么溶液？",
             ["硫酸钠", "硫酸", "浸泡"], "JTG 3432", "事实型", "JTG 3432-2024",
             tags=["新增", "方法型"]),

    # ═══════════════════════════════════════════════════════
    # JTG 3441-2024 无机结合料稳定材料 (8题)
    # ═══════════════════════════════════════════════════════
    TestCase("无机结合料稳定细粒材料的最大粒径是多少？",
             ["4.75mm", "4.75"], "JTG 3441", "事实型", "JTG 3441-2024",
             tags=["数值型"]),
    TestCase("水泥剂量用什么方法测定？",
             ["EDTA", "滴定"], "JTG 3441", "事实型", "JTG 3441-2024",
             tags=["方法型"]),
    TestCase("无机结合料稳定材料的水泥剂量用什么方法测？",
             ["EDTA", "滴定"], "JTG 3441", "事实型", "JTG 3441-2024",
             tags=["方法型"]),
    # 新增5题
    TestCase("无侧限抗压强度试件养生温度是多少？",
             ["20", "养生", "温度", "湿度"], "JTG 3441", "事实型", "JTG 3441-2024",
             tags=["新增", "数值型"]),
    TestCase("无机结合料稳定材料的击实试验分几类？",
             ["重型", "轻型", "击实"], "JTG 3441", "列举型", "JTG 3441-2024",
             tags=["新增", "分类"]),
    TestCase("无机结合料稳定材料的延迟时间对强度有什么影响？",
             ["延迟", "强度", "下降", "拌和"], "JTG 3441", "推理型", "JTG 3441-2024",
             tags=["新增", "推理型"]),
    TestCase("石灰有效钙镁含量用什么方法测定？",
             ["EDTA", "滴定", "钙镁"], "JTG 3441", "事实型", "JTG 3441-2024",
             tags=["新增", "方法型"]),
    TestCase("无机结合料稳定材料劈裂强度试验的加载速率是多少？",
             ["mm", "min", "速率", "1"], "JTG 3441", "事实型", "JTG 3441-2024",
             tags=["新增", "数值型"]),

    # ═══════════════════════════════════════════════════════
    # JTG 3430-2020 土工试验规程 (7题)
    # ═══════════════════════════════════════════════════════
    TestCase("巨粒土是指粒径大于多少毫米的土？",
             ["60mm", "60"], "JTG 3430", "事实型", "JTG 3430-2020",
             tags=["数值型"]),
    TestCase("粗粒土和细粒土的分界粒径是多少？",
             ["0.075mm", "0.075"], "JTG 3430", "事实型", "JTG 3430-2020",
             tags=["数值型"]),
    TestCase("2020版土工试验规程相比2007版新增了哪些试验？",
             ["最大承载比", "回弹模量", "动态回弹模量", "盐胀", "溶陷", "冻胀力"],
             "JTG 3430", "列举型", "JTG 3430-2020",
             tags=["版本对比"]),
    # 新增4题
    TestCase("土的液限用什么仪器测定？",
             ["液限", "锥式", "碟式", "联合测定"], "JTG 3430", "事实型", "JTG 3430-2020",
             tags=["新增", "方法型"]),
    TestCase("击实试验中土的类别用什么符号表示？",
             ["SC", "CL", "CH", "分类"], "JTG 3430", "事实型", "JTG 3430-2020",
             tags=["新增", "符号型"]),
    TestCase("CBR试验需要浸泡几天？",
             ["4天", "4昼夜", "96小时"], "JTG 3430", "事实型", "JTG 3430-2020",
             tags=["新增", "数值型"]),
    TestCase("土的压缩试验可以得到什么参数？",
             ["压缩系数", "压缩模量", "回弹指数"], "JTG 3430", "列举型", "JTG 3430-2020",
             tags=["新增", "参数型"]),

    # ═══════════════════════════════════════════════════════
    # JTG 3420-2020 水泥及水泥混凝土 (10题)
    # ═══════════════════════════════════════════════════════
    TestCase("水泥胶砂强度试验用什么方法？",
             ["ISO", "国际"], "JTG 3420", "事实型", "JTG 3420-2020",
             tags=["方法型"]),
    TestCase("混凝土抗氯离子渗透可以用哪两种方法测试？",
             ["RCM", "电通量", "氯离子"], "JTG 3420", "列举型", "JTG 3420-2020",
             tags=["耐久性"]),
    TestCase("新版水泥混凝土试验规程新增了多少项试验方法？",
             ["41", "四十一"], "JTG 3420", "事实型", "JTG 3420-2020",
             tags=["版本对比"]),
    # 新增7题
    TestCase("水泥标准稠度用水量用什么方法测定？",
             ["标准稠度", "用水量", "维卡仪"], "JTG 3420", "事实型", "JTG 3420-2020",
             tags=["新增", "方法型"]),
    TestCase("水泥胶砂流动度试验的跳桌跳动多少次？",
             ["25", "25次"], "JTG 3420", "事实型", "JTG 3420-2020",
             tags=["新增", "数值型"]),
    TestCase("水泥安定性用什么方法检验？",
             ["雷氏夹", "试饼", "煮沸"], "JTG 3420", "列举型", "JTG 3420-2020",
             tags=["新增", "方法型"]),
    TestCase("混凝土抗压强度标准试件尺寸是多少？",
             ["150mm", "立方体", "150×150×150"], "JTG 3420", "事实型", "JTG 3420-2020",
             tags=["新增", "数值型"]),
    TestCase("混凝土坍落度试验是用来评价什么的？",
             ["坍落度", "流动性", "工作性"], "JTG 3420", "推理型", "JTG 3420-2020",
             tags=["新增", "推理型"]),
    TestCase("水泥凝结时间试验中初凝和终凝怎么判定？",
             ["初凝", "终凝", "试针", "沉入"], "JTG 3420", "推理型", "JTG 3420-2020",
             tags=["新增", "推理型"]),
    TestCase("混凝土抗折强度的试件尺寸和加载方式是什么？",
             ["150×150×550", "三分点", "抗折"], "JTG 3420", "事实型", "JTG 3420-2020",
             tags=["新增", "综合"]),

    # ═══════════════════════════════════════════════════════
    # JTG E50-2006 土工合成材料 (8题)
    # ═══════════════════════════════════════════════════════
    TestCase("土工合成材料的CBR顶破强力试验编号是什么？",
             ["T1126", "1126"], "JTG E50|土工合成", "事实型", "JTG E50-2006",
             tags=["编号型"]),
    TestCase("土工合成材料耐久性试验包括哪几类？",
             ["抗氧化", "抗酸碱", "抗紫外线", "炭黑含量"], "JTG E50|土工合成", "列举型", "JTG E50-2006",
             tags=["耐久性"]),
    TestCase("土工布的宽条拉伸试验属于什么类型的性能试验？",
             ["力学", "拉伸", "宽条"], "JTG E50|土工合成", "推理型", "JTG E50-2006",
             tags=["分类"]),
    TestCase("土工合成材料有哪些耐久性试验？",
             ["抗氧化", "抗酸碱", "抗紫外线", "炭黑"], "JTG E50|土工合成", "列举型", "JTG E50-2006",
             tags=["耐久性"]),
    TestCase("土工布的CBR顶破强力试验编号多少？",
             ["T1126", "1126"], "JTG E50|土工合成", "事实型", "JTG E50-2006",
             tags=["编号型"]),
    TestCase("土工合成材料的垂直渗透用什么方法？",
             ["恒水头", "常水头", "渗透"], "JTG E50|土工合成", "事实型", "JTG E50-2006",
             tags=["方法型"]),
    # 新增2题
    TestCase("土工格栅的拉伸试验和土工布有什么区别？",
             ["格栅", "拉伸", "节点", "夹具"], "JTG E50|土工合成", "推理型", "JTG E50-2006",
             tags=["新增", "对比型"]),
    TestCase("土工膜的厚度用什么仪器测量？",
             ["厚度", "土工膜", "测厚仪", "压力"], "JTG E50|土工合成", "事实型", "JTG E50-2006",
             tags=["新增", "方法型"]),

    # ═══════════════════════════════════════════════════════
    # DB43T1206-2016 监理规范 (7题)
    # ═══════════════════════════════════════════════════════
    TestCase("公路工程监理机构一般分为哪两种形式？",
             ["总监办", "驻地办"], "DB43|监理", "事实型", "DB43T1206-2016",
             tags=["列举型"]),
    TestCase("DB43/T 1206是什么级别的标准？哪个省份的？",
             ["湖南省", "地方标准"], "DB43", "事实型", "DB43T1206-2016",
             tags=["属性型"]),
    TestCase("监理旁站项目有哪些？",
             ["旁站", "监理"], "DB43|监理", "列举型", "DB43T1206-2016",
             tags=["列举型"]),
    # 新增4题
    TestCase("监理工程师的职责包括哪些内容？",
             ["审查", "检查", "验收", "巡视"], "DB43|监理", "列举型", "DB43T1206-2016",
             tags=["新增", "职责"]),
    TestCase("监理规划和监理细则有什么区别？",
             ["规划", "细则", "监理"], "DB43", "推理型", "DB43T1206-2016",
             tags=["新增", "对比型"]),
    TestCase("公路工程监理的阶段划分是怎样的？",
             ["准备", "施工", "交工", "缺陷责任"], "DB43", "列举型", "DB43T1206-2016",
             tags=["新增", "阶段"]),
    TestCase("监理对隐蔽工程的验收程序是什么？",
             ["隐蔽", "验收", "通知", "检查"], "DB43", "推理型", "DB43T1206-2016",
             tags=["新增", "流程"]),

    # ═══════════════════════════════════════════════════════
    # JT/T1181-2018 检测等级管理 (8题)
    # ═══════════════════════════════════════════════════════
    TestCase("公路工程检测机构综合类分哪几个等级？",
             ["甲", "乙", "丙", "三个", "3个"], "JT/T1181", "列举型", "JT/T1181-2018",
             tags=["等级"]),
    TestCase("检测机构用房使用权最低年限是多少？",
             ["5年", "五年"], "JT/T1181", "事实型", "JT/T1181-2018",
             tags=["数值型"]),
    TestCase("检测人员分为哪两个级别？",
             ["助理试验检测师", "试验检测师"], "JT/T1181", "列举型", "JT/T1181-2018",
             tags=["人员"]),
    TestCase("申请公路工程综合甲级检测资质需要什么条件？",
             ["检测师", "用房", "设备"], "JT/T1181", "推理型", "JT/T1181-2018",
             tags=["综合"]),
    # 新增4题
    TestCase("检测机构等级证书有效期几年？",
             ["5年", "五年"], "JT/T1181", "事实型", "JT/T1181-2018",
             tags=["新增", "数值型"]),
    TestCase("检测机构信用等级分几级？",
             ["AA", "A", "B", "C", "D"], "JT/T1181", "列举型", "JT/T1181-2018",
             tags=["新增", "信用"]),
    TestCase("检测机构换证复核的申请时间要求？",
             ["提前", "3个月", "有效期"], "JT/T1181", "事实型", "JT/T1181-2018",
             tags=["新增", "时间"]),
    TestCase("公路工程检测项目共有多少项？",
             ["25", "25项", "检测项目"], "JT/T1181", "事实型", "JT/T1181-2018",
             tags=["新增", "数值型"]),

    # ═══════════════════════════════════════════════════════
    # 塔吊报警 (5题)
    # ═══════════════════════════════════════════════════════
    TestCase("塔吊出现报警应该怎么处理？",
             ["停止", "检查", "排除", "隐患"], "塔吊", "推理型", "塔吊报警",
             tags=["操作"]),
    TestCase("塔吊安全监控中常见的报警类型有哪些？",
             ["超载", "力矩", "高度", "幅度", "回转", "风速"], "塔吊", "列举型", "塔吊报警",
             tags=["报警"]),
    TestCase("塔吊报警分几个等级？",
             ["严重", "中等", "轻微", "三个", "3个"], "塔吊", "事实型", "塔吊报警",
             tags=["等级"]),
    # 新增2题
    TestCase("塔吊载重超限报警的严重程度属于哪个级别？",
             ["严重", "严重级"], "塔吊", "事实型", "塔吊报警",
             tags=["新增", "级别"]),
    TestCase("塔吊风速报警达到几级风需要停工？",
             ["风速", "停工", "6级", "风力"], "塔吊", "事实型", "塔吊报警",
             tags=["新增", "数值型"]),

    # ═══════════════════════════════════════════════════════
    # 跨文档对比推理 (10题)
    # ═══════════════════════════════════════════════════════
    TestCase("JTG 3432和JTG 3441中细粒材料的分界粒径一样吗？",
             ["4.75mm", "4.75", "2.36mm"], "JTG 3432|JTG 3441", "跨文档", "JTG 3432-2024+JTG 3441-2024",
             tags=["跨文档", "对比"]),
    TestCase("JTG 3420和JTG 3441都涉及水泥试验，它们分别侧重什么？",
             ["水泥", "混凝土", "无机结合料", "材料"], "JTG 3420|JTG 3441", "跨文档", "JTG 3420-2020+JTG 3441-2024",
             tags=["跨文档", "对比"]),
    TestCase("集料试验规程中细集料的定义和土工试验规程一样吗？",
             ["4.75mm", "0.075mm", "不同"], "JTG 3432|JTG 3430", "跨文档", "JTG 3432-2024+JTG 3430-2020",
             tags=["跨文档", "对比"]),
    TestCase("岩石试验规程和土工试验规程哪个包含CBR试验？",
             ["CBR", "土工", "岩石", "3430"], "JTG 3431|JTG 3430", "跨文档", "JTG 3431-2024+JTG 3430-2020",
             tags=["跨文档", "判断"]),
    TestCase("检测频率取样要求（常用45项）和检测等级管理要求（JT/T1181）分别管什么？",
             ["频率", "取样", "等级", "资质"], "常用45项|JT/T1181", "跨文档", "常用45项+JT/T1181-2018",
             tags=["跨文档", "对比"]),
    # 新增5题跨文档
    TestCase("水泥混凝土试验规程和集料试验规程中，集料粒径分类标准有什么不同？",
             ["4.75mm", "2.36mm", "水泥混凝土", "沥青"], "JTG 3420|JTG 3432", "跨文档", "JTG 3420-2020+JTG 3432-2024",
             tags=["新增", "跨文档"]),
    TestCase("土工试验规程中的CBR试验和无机结合料中的CBR试验有什么不同？",
             ["CBR", "土工", "无机结合料", "不同"], "JTG 3430|JTG 3441", "跨文档", "JTG 3430-2020+JTG 3441-2024",
             tags=["新增", "跨文档"]),
    TestCase("监理规范和检验评定标准在质量管控中分别起什么作用？",
             ["监理", "评定", "管控", "质量"], "DB43|JTG F80", "跨文档", "DB43T1206-2016+JTG F80-1-2017",
             tags=["新增", "跨文档"]),
    TestCase("集料试验和岩石试验中密度测定的方法有什么异同？",
             ["密度", "表观", "量积", "水中称量"], "JTG 3432|JTG 3431", "跨文档", "JTG 3432-2024+JTG 3431-2024",
             tags=["新增", "跨文档"]),
    TestCase("45项检测项目和检测等级管理中关于人员要求有什么关联？",
             ["人员", "检测师", "频率", "等级"], "常用45项|JT/T1181", "跨文档", "常用45项+JT/T1181-2018",
             tags=["新增", "跨文档"]),

    # ═══════════════════════════════════════════════════════
    # 新增文档：检测频率Excel (5题)
    # ═══════════════════════════════════════════════════════
    TestCase("路基填筑材料每层检测哪些项目？",
             ["压实度", "含水率", "厚度", "宽度"], "检测频率", "列举型", "检测频率",
             tags=["新增", "Excel文档"]),
    TestCase("桥梁桩基检测的频率和取样数量是多少？",
             ["桩基", "声测", "取芯", "频率"], "检测频率", "事实型", "检测频率",
             tags=["新增", "Excel文档"]),
    TestCase("隧道锚杆拉拔力检测频率是多少？",
             ["锚杆", "拉拔", "频率", "数量"], "检测频率", "事实型", "检测频率",
             tags=["新增", "Excel文档"]),
    TestCase("路面面层厚度检测用什么方法？",
             ["钻芯", "雷达", "厚度", "路面"], "检测频率", "事实型", "检测频率",
             tags=["新增", "Excel文档"]),
    TestCase("交通安全设施中波形梁护栏的检测项目有哪些？",
             ["波形梁", "护栏", "镀锌", "厚度"], "检测频率", "列举型", "检测频率",
             tags=["新增", "Excel文档"]),
]


# ============================================================
# 评估逻辑（同v3）
# ============================================================

def evaluate_basic(answer: str, sources: list, tc: TestCase) -> Dict:
    source_texts = []
    source_docs = []
    for s in sources:
        sd = getattr(s, 'doc_name', '') or ''
        sc = getattr(s, 'content', '') or ''
        source_docs.append(sd)
        source_texts.append(sc)

    all_text = ' '.join(source_texts) + ' ' + answer

    kw_hits_src = 0
    kw_hits_ans = 0
    kw_total = len(tc.expected_keywords)
    for kw in tc.expected_keywords:
        kwl = kw.lower()
        if kwl in all_text.lower():
            kw_hits_src += 1
        if kwl in answer.lower():
            kw_hits_ans += 1

    recall = kw_hits_src / kw_total if kw_total else 0
    precision = kw_hits_ans / kw_total if kw_total else 0
    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0

    src_pat = re.compile(tc.expected_doc, re.IGNORECASE)
    src_match = any(src_pat.search(d) for d in source_docs)

    return {
        "recall": round(recall, 3),
        "precision": round(precision, 3),
        "f1": round(f1, 3),
        "src_match": src_match,
        "src_docs": list(set(source_docs[:5])),
        "answer_preview": answer[:300],
    }


# ============================================================
# 主评估流程
# ============================================================

async def run():
    # 加载BM25索引
    from app.config import get_settings
    settings = get_settings()
    bm25_path = Path(settings.BM25_INDEX_PATH)
    if bm25_path.exists():
        from app.retrievers.bm25_retriever import load_bm25_retriever
        load_bm25_retriever(str(bm25_path))
        print(f"BM25索引已加载: {bm25_path}\n")

    orchestrator = get_orchestrator()
    results = []
    n = len(TEST_CASES)

    categories = {}
    doc_coverage = {}

    print(f"\n{'='*70}")
    print(f"  RAG 系统全量评估 v4 — {n} 个用例，覆盖多份文档+多种类型")
    print(f"{'='*70}\n")

    for i, tc in enumerate(TEST_CASES):
        print(f"[{i+1:3d}/{n}] {tc.category:6s} | {tc.question[:55]}...")

        start = time.time()
        result = await orchestrator.process_query(
            question=tc.question, use_web_search=False, top_k=5, use_cache=False
        )
        elapsed = int((time.time() - start) * 1000)

        ev = evaluate_basic(result.answer, result.sources, tc)

        row = {
            "id": i + 1,
            "question": tc.question,
            "category": tc.category,
            "doc_source": tc.doc_source,
            "expected_keywords": tc.expected_keywords,
            "tags": tc.tags,
            "answer": result.answer,
            "recall": ev["recall"],
            "precision": ev["precision"],
            "f1": ev["f1"],
            "src_match": ev["src_match"],
            "src_docs": ev["src_docs"],
            "answer_preview": ev["answer_preview"],
            "time_ms": elapsed,
        }
        results.append(row)

        # 分类统计
        for cat in [tc.category]:
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(row)

        doc_key = tc.doc_source.split("+")[0].strip()
        if doc_key not in doc_coverage:
            doc_coverage[doc_key] = []
        doc_coverage[doc_key].append(row)

        # 行内结果显示
        icon = "✅" if ev["f1"] >= 0.7 else ("⚠️" if ev["f1"] >= 0.3 else "❌")
        print(f"     {icon} F1={ev['f1']:.1%} R={ev['recall']:.1%} P={ev['precision']:.1%}"
              f" | {'✓源' if ev['src_match'] else '✗源'} {elapsed}ms | {ev['answer_preview'][:60]}...")

    # 汇总
    def mean(vals):
        v = list(vals)
        return sum(v) / len(v) if v else 0

    print(f"\n{'='*70}")
    print(f"  评估汇总 (v4)")
    print(f"{'='*70}")

    overall_f1 = mean(r["f1"] for r in results)
    overall_recall = mean(r["recall"] for r in results)
    overall_precision = mean(r["precision"] for r in results)
    overall_src_hit = sum(r["src_match"] for r in results) / n
    overall_time = mean(r["time_ms"] for r in results)

    print(f"  总用例数: {n}")
    print(f"  F1 Score: {overall_f1:.1%}")
    print(f"  Recall:   {overall_recall:.1%}")
    print(f"  Precision: {overall_precision:.1%}")
    print(f"  来源命中: {overall_src_hit:.1%} ({sum(r['src_match'] for r in results)}/{n})")
    print(f"  均耗时:    {overall_time:.0f}ms")

    print(f"\n  ── 按问题类型 ──")
    for cat, rows in sorted(categories.items(), key=lambda x: -mean(r["f1"] for r in x[1])):
        m = mean(r["f1"] for r in rows)
        print(f"    {cat:12s}: F1={m:.1%} ({len(rows)}题)")

    print(f"\n  ── 按目标文档 ──")
    for doc, rows in sorted(doc_coverage.items(), key=lambda x: -mean(r["f1"] for r in x[1])):
        m = mean(r["f1"] for r in rows)
        hit = sum(r["src_match"] for r in rows) / len(rows) if rows else 0
        print(f"    {doc:25s}: F1={m:.1%} 源命中={hit:.0%} ({len(rows)}题)")

    # 低分用例
    print(f"\n  ── 需要改进的用例 (F1<0.5) ──")
    low = sorted([r for r in results if r["f1"] < 0.5], key=lambda r: r["f1"])
    for r in low:
        print(f"    [{r['id']:3d}] F1={r['f1']:.1%} | {r['question'][:60]}")
        print(f"          答案: {r['answer_preview'][:120]}")
        print(f"          来源: {', '.join(r['src_docs'][:3] or ['无'])}")

    # 保存报告
    import os
    report_dir = Path("docs/RAG效果优化")
    report_dir.mkdir(parents=True, exist_ok=True)

    # 保存汇总
    summary = {
        "version": "v4",
        "total_cases": n,
        "avg_recall": round(overall_recall, 3),
        "avg_precision": round(overall_precision, 3),
        "avg_f1": round(overall_f1, 3),
        "source_hit_rate": round(overall_src_hit, 3),
        "avg_time_ms": round(overall_time, 1),
        "by_category": {
            cat: {
                "count": len(rows),
                "avg_f1": round(mean(r["f1"] for r in rows), 3),
                "source_hit": round(sum(r["src_match"] for r in rows) / len(rows), 3),
            }
            for cat, rows in categories.items()
        },
        "by_document": {
            doc: {
                "count": len(rows),
                "avg_f1": round(mean(r["f1"] for r in rows), 3),
                "source_hit": round(sum(r["src_match"] for r in rows) / len(rows), 3),
            }
            for doc, rows in doc_coverage.items()
        },
    }

    with open(report_dir / "evaluation_v4.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 保存详细报告
    detailed = {
        "version": "v4",
        "summary": summary,
        "details": results,
    }
    with open(report_dir / "evaluation_v4_detail.json", "w", encoding="utf-8") as f:
        json.dump(detailed, f, ensure_ascii=False, indent=2)

    print(f"\n  报告已保存: {report_dir / 'evaluation_v4.json'}")
    print(f"  详细报告:   {report_dir / 'evaluation_v4_detail.json'}")


if __name__ == "__main__":
    asyncio.run(run())
