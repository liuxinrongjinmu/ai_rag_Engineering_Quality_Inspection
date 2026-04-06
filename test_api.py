"""
工程质检RAG系统 API测试脚本
"""
import httpx
import json
import time


def test_query(question: str, use_web_search: bool = True, top_k: int = 5):
    """
    测试问答接口
    
    :param question: 问题
    :param use_web_search: 是否使用网络检索
    :param top_k: 返回结果数
    """
    print(f"\n{'='*60}")
    print(f"问题: {question}")
    print('='*60)
    
    start_time = time.time()
    
    try:
        response = httpx.post(
            'http://localhost:5002/api/v1/query',
            json={
                'question': question,
                'options': {
                    'use_web_search': use_web_search,
                    'top_k': top_k
                }
            },
            timeout=120.0
        )
        
        elapsed_time = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()['data']
            
            print(f"\n【答案】")
            print(data['answer'])
            
            sources = data['sources']
            unique_docs = {}
            for source in sources:
                doc_name = source.get('doc_name', '未知文档')
                if doc_name not in unique_docs:
                    unique_docs[doc_name] = source
            
            print(f"\n【来源信息】({len(unique_docs)}个文档)")
            for i, (doc_name, source) in enumerate(unique_docs.items(), 1):
                source_type = source.get('source_type', 'local')
                if source_type == 'web':
                    print(f"  {i}. {doc_name}")
                    if source.get('url'):
                        print(f"     URL: {source['url']}")
                    print(f"     类型: 网络来源")
                else:
                    print(f"  {i}. {doc_name}")
                    if source.get('page'):
                        print(f"     页码: 第{source['page']}页")
                    if source.get('section'):
                        print(f"     章节: {source['section']}")
                    print(f"     类型: 本地知识库")
            
            print(f"\n【统计信息】")
            print(f"  服务器耗时: {data['query_time_ms']}ms")
            print(f"  实际耗时: {elapsed_time:.2f}s")
            print(f"  使用网络检索: {'是' if data['used_web_search'] else '否'}")
        else:
            print(f"请求失败: {response.status_code}")
            print(response.text)
            
    except httpx.ConnectError:
        print("错误: 无法连接到服务器，请确保服务已启动 (python -m app.main)")
    except Exception as e:
        print(f"错误: {e}")


def test_health():
    """
    测试健康检查接口
    """
    print("\n" + "="*60)
    print("健康检查")
    print("="*60)
    
    try:
        response = httpx.get('http://localhost:5002/api/v1/health', timeout=10.0)
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n系统状态: {data['status']}")
            print(f"\n组件状态:")
            for component, status in data['components'].items():
                status_icon = "✓" if status == "ok" else "✗"
                print(f"  {status_icon} {component}: {status}")
            print(f"\n数据统计:")
            print(f"  - 总切片数: {data['stats']['total_chunks']}")
            print(f"  - 总文档数: {data['stats']['total_docs']}")
        else:
            print(f"请求失败: {response.status_code}")
            
    except httpx.ConnectError:
        print("错误: 无法连接到服务器，请确保服务已启动 (python -m app.main)")
    except Exception as e:
        print(f"错误: {e}")


def interactive_mode():
    """
    交互模式
    """
    print("\n" + "="*60)
    print("工程质检RAG系统 - 交互测试模式")
    print("="*60)
    print("输入问题进行测试，输入 'quit' 或 'exit' 退出")
    print("输入 'health' 检查系统状态")
    
    while True:
        try:
            question = input("\n请输入问题: ").strip()
            
            if not question:
                continue
            
            if question.lower() in ['quit', 'exit', 'q']:
                print("退出测试")
                break
            
            if question.lower() == 'health':
                test_health()
                continue
            
            test_query(question)
            
        except KeyboardInterrupt:
            print("\n退出测试")
            break


def main():
    """
    主函数
    """
    print("\n" + "="*60)
    print("工程质检RAG系统 - API测试工具")
    print("="*60)
    print("\n选择测试模式:")
    print("  1. 运行预设测试场景")
    print("  2. 交互模式")
    print("  3. 健康检查")
    print("  4. 退出")
    
    choice = input("\n请选择 (1-4): ").strip()
    
    if choice == '1':
        test_questions = [
            "粉煤灰检测项目有哪些",
            "锚具检测频率是多少",
            "钢绞线取样方法",
            "土方路基压实度检测频率",
            "水泥混凝土试验规程"
        ]
        
        for q in test_questions:
            test_query(q)
            
    elif choice == '2':
        interactive_mode()
        
    elif choice == '3':
        test_health()
        
    elif choice == '4':
        print("退出")
    else:
        print("无效选择")


if __name__ == "__main__":
    main()
