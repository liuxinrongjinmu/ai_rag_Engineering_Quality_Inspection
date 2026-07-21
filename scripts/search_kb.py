"""在知识库中搜索特定关键词"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.infrastructure.vectorstore import get_vectorstore

vs = get_vectorstore()
col = vs._collection

# 搜索96%
r = col.get(include=['documents', 'metadatas'], limit=99999)
ids = r.get('ids', [])
docs = r.get('documents', [])
metas = r.get('metadatas', [])

print("=== 含 '96%' 的切片 ===")
for i in range(len(ids)):
    if '96%' in docs[i]:
        print(f"  [{metas[i].get('doc_name','')}] type={metas[i].get('chunk_type','')} idx={metas[i].get('chunk_index','')}")
        print(f"  {docs[i][:300]}")
        print()

print("\n=== 含 '4.75mm' 且含 '细粒' 的切片 ===")
for i in range(len(ids)):
    if '4.75mm' in docs[i] and '细粒' in docs[i]:
        print(f"  [{metas[i].get('doc_name','')}] type={metas[i].get('chunk_type','')} idx={metas[i].get('chunk_index','')}")
        print(f"  {docs[i][:300]}")
        print()

print("\n=== 含 '上路床' 的切片 ===")
for i in range(len(ids)):
    if '上路床' in docs[i]:
        print(f"  [{metas[i].get('doc_name','')}] type={metas[i].get('chunk_type','')} idx={metas[i].get('chunk_index','')}")
        print(f"  {docs[i][:300]}")
        print()

print("\n=== 含 '每压实层' 的切片 ===")
for i in range(len(ids)):
    if '每压实层' in docs[i]:
        print(f"  [{metas[i].get('doc_name','')}] type={metas[i].get('chunk_type','')} idx={metas[i].get('chunk_index','')}")
        print(f"  {docs[i][:300]}")
        print()
