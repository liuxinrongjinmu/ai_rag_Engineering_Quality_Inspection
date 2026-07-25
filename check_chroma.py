"""检查 chromadb 中常用45项文档的切片"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.infrastructure.vectorstore import get_vectorstore

vectorstore = get_vectorstore()
collection = vectorstore._collection

# 按 doc_id 过滤
doc_id = "ee787f4b5d46ac25"
results = collection.get(where={"doc_id": doc_id}, include=["metadatas", "documents"])

print(f"doc_id={doc_id} 的切片数: {len(results['documents'])}")
overview_count = sum(1 for m in results["metadatas"] if m.get("chunk_type") == "overview")
print(f"其中 overview 切片数: {overview_count}")
for i, (doc, meta) in enumerate(zip(results["documents"], results["metadatas"])):
    if meta.get("chunk_type") != "overview":
        continue
    print(f"\n--- 切片 {i} (chunk_type={meta.get('chunk_type')}, chunk_index={meta.get('chunk_index')}) ---")
    print(doc[:2000])
