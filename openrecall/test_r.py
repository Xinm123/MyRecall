import requests
import json
import os


API_KEY = "sk-yowawdangondqlezbiwulngweoqcauqkuhozedcidzcrdrjk"

# 硅基流动 Rerank 官方端点
BASE_URL = "https://api.siliconflow.cn/v1/rerank"


MODEL_NAME = "Qwen/Qwen3-Reranker-0.6B" 

def rerank_with_siliconflow(query, documents, top_n=None):
    """
    使用 SiliconFlow API 进行文档重排序
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL_NAME,
        "query": query,
        "documents": documents,
        "top_n": top_n or len(documents),
        "return_documents": True, # 返回文档内容方便查看
        "max_chunks_per_doc": 1024,
        "overlap_tokens": 80
    }
    
    try:
        print(f"正在请求 SiliconFlow ({MODEL_NAME})...")
        response = requests.post(BASE_URL, headers=headers, json=payload)
        
        # 错误处理
        if response.status_code != 200:
            print(f"API Error {response.status_code}: {response.text}")
            return []
            
        result = response.json()
        
        # 解析标准响应格式
        if "results" in result:
            return result["results"]
        else:
            print(f"未预期的响应格式: {result}")
            return []

    except requests.exceptions.RequestException as e:
        print(f"网络请求失败: {e}")
        return []

# --- 在 OpenRecall 场景下的测试 ---
if __name__ == "__main__":
    # 模拟 OpenRecall 召回的混合内容（OCR识别文本 + 描述）
    user_query = "上周我看过的那个关于 Windows Recall 架构的 PDF 放在哪了？"
    
    candidate_docs = [
        "文件名: recipe_tomato_eggs.pdf | 内容: 番茄炒蛋的做法需要准备...",
        "文件名: architecture_diagram.png | 内容: Windows Recall 使用 client-side NPU 进行截图处理...", 
        "文件名: meeting_notes.txt | 内容: 上周五会议讨论了 OpenRecall 的后端 API 设计...",
        "文件名: system_setup.md | 内容: 在 Debian 上配置 Python 环境..."
    ]

    ranked_results = rerank_with_siliconflow(user_query, candidate_docs, top_n=3)

    print(f"\n查询: {user_query}")
    print("-" * 50)
    for item in ranked_results:
        # SiliconFlow 返回的结构通常包含 index, relevance_score, document
        doc_content = item.get('document', {}).get('text', candidate_docs[item['index']])
        print(f"分数: {item['relevance_score']:.4f} | 文档: {doc_content[:30]}...")