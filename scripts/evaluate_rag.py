"""
RAG 系统量化评估脚本 v2
合并检索+LLM为一次调用，快速评估召回率和准确率
"""
import sys
import asyncio
import re
import json
from pathlib import Path
from typing import List
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.orchestrator import get_orchestrator


@dataclass
class TestCase:
    question: str
    expected_keywords: List[str]
    expected_doc_pattern: str
    category: str
    doc_source: str


TEST_CASES = [
    # ---- 质量检验评定标准 ----
    TestCase("公路工程质量检验评定中，关键项目的合格率应不低于多少？",
             ["95%", "百分之九十五"], "JTG F80", "事实型", "JTG F80-1-2017"),
    TestCase("高速公路和一级公路上路床的压实度要求不低于多少？",
             ["96%", "百分之九十六"], "JTG F80", "事实型", "JTG F80-1-2017"),
    TestCase("一般项目的合格率应不低于多少？",
             ["80%", "百分之八十"], "JTG F80", "事实型", "JTG F80-1-2017"),

    # ---- 检测频率 ----
    TestCase("土方路基每200m每压实层施工自检测几处？",
             ["4处"], "常用45项|检测频率", "事实型", "常用45项"),
    TestCase("钢筋原材施工自检每批不超过多少吨？",
             ["60"], "常用45项", "事实型", "常用45项"),
    TestCase("道路石油沥青进场每批不超过多少吨？",
             ["2000"], "常用45项", "事实型", "常用45项"),
    TestCase("水泥剂量施工自检每多少小时抽检1组？",
             ["2小时", "两小时"], "常用45项", "事实型", "常用45项"),
    TestCase("底基层和基层压实度每200m每车道测几处？",
             ["2处", "每车道"], "常用45项", "事实型", "常用45项"),

    # ---- 岩石试验规程 ----
    TestCase("含水率试验每组试件数量是多少？",
             ["5个", "五个"], "岩石试验|JTG 3431", "事实型", "JTG 3431-2024"),
    TestCase("岩石单轴抗压强度标准试件直径是多少？",
             ["50mm", "50毫米"], "岩石试验|JTG 3431", "事实型", "JTG 3431-2024"),

    # ---- 集料试验规程 ----
    TestCase("沥青混合料中粗集料粒径大于多少mm？",
             ["2.36mm", "2.36"], "集料试验|JTG 3432", "事实型", "JTG 3432-2024"),
    TestCase("水泥混凝土中细集料粒径小于多少mm？",
             ["4.75mm", "4.75"], "集料试验|JTG 3432", "事实型", "JTG 3432-2024"),

    # ---- 无机结合料 ----
    TestCase("无机结合料稳定细粒材料最大粒径不超过多少？",
             ["4.75mm", "4.75"], "无机结合料|JTG 3441", "事实型", "JTG 3441-2024"),

    # ---- 检测等级管理 ----
    TestCase("公路工程检测机构等级分哪几类？",
             ["综合类", "专项类", "甲乙丙"], "JT.T1181|检测等级", "事实型", "JT/T1181-2018"),
    TestCase("检测机构用房使用权最低年限是多少？",
             ["5年", "五年"], "JT.T1181|检测等级", "事实型", "JT/T1181-2018"),

    # ---- 推理型 ----
    TestCase("监理抽检频率一般为施工单位的多少比例？",
             ["20%", "百分之二十"], "监理|常用45项", "推理型", "常用45项+监理规范"),
    TestCase("分项工程质量评定合格条件有哪些？",
             ["检验记录", "实测项目"], "JTG F80", "推理型", "JTG F80-1-2017"),
]


def evaluate(answer: str, sources: list, tc: TestCase):
    """综合评估召回+准确率"""
    # 召回率：检查来源文档和切片内容是否匹配
    source_docs = [getattr(s, 'doc_name', '') for s in sources]
    source_pattern = re.compile(tc.expected_doc_pattern, re.IGNORECASE)
    src_match = any(source_pattern.search(d) for d in source_docs)

    source_contents = [getattr(s, 'content', '') for s in sources]
    all_text = ' '.join(source_contents) + ' ' + answer

    kw_matched = sum(1 for kw in tc.expected_keywords if kw.lower() in all_text.lower())
    kw_total = len(tc.expected_keywords)
    recall_rate = kw_matched / kw_total if kw_total else 0

    # 准确率：答案中是否包含目标关键词
    ans_matched = sum(1 for kw in tc.expected_keywords if kw.lower() in answer.lower())
    precision_rate = ans_matched / kw_total if kw_total else 0

    return {
        "src_match": src_match,
        "recall_rate": round(recall_rate, 2),
        "precision_rate": round(precision_rate, 2),
        "recalled": recall_rate >= 0.5,
        "precise": precision_rate >= 0.5,
        "answer": answer[:200],
    }


async def run():
    orchestrator = get_orchestrator()
    results = []
    recalled = precise = src_acc = 0

    print(f"\n{'='*65}")
    print(f"  RAG 量化评估 - {len(TEST_CASES)} 用例")
    print(f"{'='*65}\n")

    for i, tc in enumerate(TEST_CASES):
        result = await orchestrator.process_query(
            question=tc.question, use_web_search=False, top_k=5, use_cache=False
        )

        ev = evaluate(result.answer, result.sources, tc)
        if ev["recalled"]:
            recalled += 1
        if ev["precise"]:
            precise += 1
        if ev["src_match"]:
            src_acc += 1

        status = "✅" if ev["recalled"] and ev["precise"] else ("⚠️" if ev["recalled"] else "❌")
        print(f"[{i+1:2d}/{len(TEST_CASES)}] {tc.question}")
        print(f"    召回={ev['recall_rate']:.0%} {'OK' if ev['recalled'] else 'FAIL'} | "
              f"准确={ev['precision_rate']:.0%} {'OK' if ev['precise'] else 'FAIL'} | "
              f"来源={'OK' if ev['src_match'] else 'MISS'} | {tc.category} {status}")
        print(f"    答: {ev['answer'][:120]}")

        results.append({"question": tc.question, "category": tc.category,
                        "doc_source": tc.doc_source, **ev,
                        "time_ms": result.query_time_ms})
        print()

    # 汇总
    n = len(TEST_CASES)
    fact = [r for r in results if r["category"] == "事实型"]
    reason = [r for r in results if r["category"] == "推理型"]
    f_recall = sum(1 for r in fact if r["recalled"]) / len(fact) if fact else 0
    f_prec = sum(1 for r in fact if r["precise"]) / len(fact) if fact else 0
    r_recall = sum(1 for r in reason if r["recalled"]) / len(reason) if reason else 0
    r_prec = sum(1 for r in reason if r["precise"]) / len(reason) if reason else 0

    print(f"{'='*65}")
    print(f"  📊 评估报告")
    print(f"{'='*65}")
    print(f"  总用例:       {n:2d}")
    print(f"  召回(>=50%):  {recalled}/{n}  ({recalled/n:.0%})  均值: {sum(r['recall_rate'] for r in results)/n:.0%}")
    print(f"  准确(>=50%):  {precise}/{n}  ({precise/n:.0%})  均值: {sum(r['precision_rate'] for r in results)/n:.0%}")
    print(f"  来源命中:     {src_acc}/{n}  ({src_acc/n:.0%})")
    print(f"  事实型({len(fact)}): 召回={f_recall:.0%} 准确={f_prec:.0%}")
    print(f"  推理型({len(reason)}): 召回={r_recall:.0%} 准确={r_prec:.0%}")
    print(f"  均耗时:       {sum(r['time_ms'] for r in results)/n:.0f}ms")

    failed = [r for r in results if not r["recalled"] or not r["precise"]]
    if failed:
        print(f"\n  ─── 需改进 ({len(failed)}/{n}) ───")
        for f in failed:
            print(f"  ❌ {f['question']}")
            print(f"     R={f['recall_rate']:.0%} P={f['precision_rate']:.0%} → {f['answer'][:100]}")

    print(f"{'='*65}\n")

    out = Path(__file__).parent.parent / "docs" / "RAG效果优化" / "evaluation_v2.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": n, "recalled": recalled, "recall_pct": round(recalled/n, 3),
                "precise": precise, "precision_pct": round(precise/n, 3),
                "src_match": src_acc,
                "fact_recall": round(f_recall, 3), "fact_precision": round(f_prec, 3),
                "reason_recall": round(r_recall, 3), "reason_precision": round(r_prec, 3),
                "avg_time_ms": round(sum(r['time_ms'] for r in results)/n, 0),
            },
            "details": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {out}")


if __name__ == "__main__":
    asyncio.run(run())
