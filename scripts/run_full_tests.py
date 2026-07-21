"""
RAG问答系统 — 全文档系统性测试
针对8份知识库文档，每份3-4个问题，覆盖核心内容、关键细节、应用场景
"""
import json, urllib.request, time, sys

BASE = "http://localhost:5002/api/v1/query"

# 测试用例：8份文档 × 3-4题 = 28题
TEST_CASES = [
    # ===== 1. DB43T1206-2016公路工程监理规范 =====
    {
        "doc": "DB43T1206-2016公路工程监理规范",
        "questions": [
            ("核心内容", "公路工程监理机构一般应设置哪些部门？"),
            ("关键细节", "施工准备阶段监理工程师主要要做哪些工作？"),
            ("应用场景", "施工现场出现质量问题，监理应该怎么处理？"),
        ]
    },
    # ===== 2. JTG 3431-2024 公路工程岩石试验规程 =====
    {
        "doc": "JTG 3431-2024 公路工程岩石试验规程",
        "questions": [
            ("核心内容", "岩石试验主要包含哪些检测项目？"),
            ("关键细节", "岩石含水率试验采用什么方法？"),
            ("应用场景", "岩石的单轴抗压强度怎么测？"),
        ]
    },
    # ===== 3. JTG F80-1-2017 公路工程质量检验评定标准 =====
    {
        "doc": "JTG F80-1-2017 公路工程质量检验评定标准 第一册 土建工程",
        "questions": [
            ("核心内容", "公路工程质量检验评定采用什么方法？"),
            ("关键细节", "土方路基压实度的检验频率是多少？"),
            ("关键细节", "上路床的压实度要求不低于多少？"),
            ("应用场景", "路面工程的质量评定包含哪些检查项目？"),
        ]
    },
    # ===== 4. JTG 3432-2024 公路工程集料试验规程 =====
    {
        "doc": "JTG 3432-2024 公路工程集料试验规程",
        "questions": [
            ("核心内容", "集料试验规程包含哪些类型的集料？"),
            ("关键细节", "粗集料压碎值试验怎么做？"),
            ("应用场景", "粗集料的密度和吸水率怎么测定？"),
        ]
    },
    # ===== 5. 公路工程水泥及水泥混凝土试验规程 =====
    {
        "doc": "公路工程水泥及水泥混凝土试验规程（JTG 3420-2020）",
        "questions": [
            ("核心内容", "水泥的细度用什么方法测定？"),
            ("关键细节", "水泥标准稠度用水量怎么确定？"),
            ("应用场景", "混凝土坍落度试验的操作步骤是什么？"),
        ]
    },
    # ===== 6. 常用45项公路试验检测项目、频率及取样要求 =====
    {
        "doc": "常用45项公路试验检测项目、频率及取样要求",
        "questions": [
            ("核心内容", "路基压实度检测的频率要求是什么？"),
            ("关键细节", "水泥的取样方法和取样数量是多少？"),
            ("应用场景", "钢筋原材进场需要检测哪些项目？"),
        ]
    },
    # ===== 7. JTG 3441-2024 公路工程无机结合料稳定材料试验规程 =====
    {
        "doc": "JTG 3441-2024 公路工程无机结合料稳定材料试验规程",
        "questions": [
            ("核心内容", "无机结合料稳定材料主要包含哪些类型？"),
            ("关键细节", "水泥剂量用什么方法测定？"),
            ("关键细节", "无机结合料稳定材料中细粒材料最大粒径不超过多少？"),
            ("应用场景", "无机结合料稳定材料的无侧限抗压强度怎么测？"),
        ]
    },
    # ===== 8. 公路土工试验规程2020 =====
    {
        "doc": "公路土工试验规程2020",
        "questions": [
            ("核心内容", "土的工程分类有哪些大类？"),
            ("关键细节", "土的含水率用什么方法测定？"),
            ("应用场景", "土的液限和塑限怎么测定？"),
        ]
    },
]

results = []
total = sum(len(tc["questions"]) for tc in TEST_CASES)
current = 0

print(f"{'='*70}")
print(f"RAG问答系统 — 全文档系统性测试")
print(f"文档数: {len(TEST_CASES)} | 总问题数: {total}")
print(f"{'='*70}")

for tc in TEST_CASES:
    doc_name = tc["doc"]
    print(f"\n{'─'*70}")
    print(f"📄 {doc_name}")
    print(f"{'─'*70}")

    for qtype, question in tc["questions"]:
        current += 1
        print(f"\n  [{current}/{total}] [{qtype}] 问: {question}")
        
        try:
            data = json.dumps({
                "question": question,
                "options": {"use_web_search": False, "top_k": 5}
            }).encode()
            req = urllib.request.Request(BASE, data=data, headers={"Content-Type": "application/json"})
            start = time.time()
            with urllib.request.urlopen(req, timeout=90) as resp:
                resp_data = json.loads(resp.read())
            elapsed = int((time.time() - start) * 1000)
            
            answer = resp_data.get("data", {}).get("answer", "无回答")
            sources = resp_data.get("data", {}).get("sources", [])
            source_doc = sources[0].get("doc_name", "?") if sources else "无来源"
            status = resp_data.get("code", -1)
            
            # 简化输出（分两行）
            print(f"      答: {answer[:150]}{'...' if len(answer) > 150 else ''}")
            print(f"      来源: {source_doc[:50]} | 耗时: {elapsed}ms | 状态码: {status}")
            
            results.append({
                "doc": doc_name,
                "type": qtype,
                "question": question,
                "answer": answer,
                "source": source_doc,
                "elapsed_ms": elapsed,
                "status": status,
                "answer_length": len(answer),
            })
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"      错误: {str(e)[:100]}")
            results.append({
                "doc": doc_name,
                "type": qtype,
                "question": question,
                "answer": f"ERROR: {str(e)[:200]}",
                "source": "N/A",
                "elapsed_ms": -1,
                "status": -1,
                "answer_length": 0,
            })

# 写入结果
output_path = "/Users/jinmu/Desktop/金木/my-project/工程质检RAG系统/logs/test_results.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n{'='*70}")
print(f"测试完成！结果已保存: {output_path}")
print(f"共 {len(results)} 个问题")
