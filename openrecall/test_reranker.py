import requests
import json

# 1. 配置参数
API_TOKEN = "ms-230d5d2f-de65-406f-9563-f30d82b9eb9b" # 确保在 modelscope.cn 设置中获取
MODEL_ID = "Qwen/Qwen3-Reranker-0.6B"

# ModelScope 原生推理 API 地址格式
# 注意：这里不是 /v1/rerank，而是 /api-inference/v1/models/{model_id}
API_URL = f"https://api-inference.modelscope.cn/api-inference/v1/models/{MODEL_ID}"

def rerank_documents(query, documents):
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }

    # 2. 构建符合 ModelScope text-ranking 任务的 Payload
    payload = {
        "input": {
            "source_sentence": query,
            "sentences_to_compare": documents
        },
        "parameters": {} # 可选参数
    }

    try:
        print(f"正在调用 ModelScope 原生接口: {API_URL}")
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        # 3. 解析返回结果
        # ModelScope 返回格式通常为: {"Data": {"scores": [0.98, 0.12, ...]}}
        result_data = response.json()
        
        if "Data" in result_data and "scores" in result_data["Data"]:
            scores = result_data["Data"]["scores"]
            
            # 将分数与文档组合并排序
            ranked_results = []
            for idx, score in enumerate(scores):
                ranked_results.append({
                    "index": idx,
                    "relevance_score": score,
                    "document": documents[idx]
                })
            
            # 按分数降序排列
            ranked_results.sort(key=lambda x: x["relevance_score"], reverse=True)
            return ranked_results
        else:
            print(f"返回结构异常: {result_data}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        if 'response' in locals() and response.text:
            print(f"错误详情: {response.text}")
        return None

# --- 测试 ---
if __name__ == "__main__":
    query = "如何配置 Linux 服务器环境？"
    docs = [
        "在 Debian 上安装 Python 环境需要使用 apt install python3...",
        "做番茄炒蛋需要准备三个鸡蛋...", 
        "配置 systemd 服务可以实现开机自启..."
    ]

    results = rerank_documents(query, docs)
    
    if results:
        for item in results:
            print(f"分数: {item['relevance_score']:.4f} | 内容: {item['document'][:20]}...")