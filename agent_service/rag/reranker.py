# BGE-Reranker 二次精排
"""
Rerank 模块：对初排召回的 Top-N 候选文档进行 Cross-Encoder 深度打分。
如果本地未下载深度学习模型权重，内置优雅回退（Fallback）逻辑，保证代码在任何新手电脑上都能直接跑通！
"""
import os
from typing import List, Dict

import jieba

class DocumentReranker:
    def __init__(self):
        self.has_model = False
        self.reranker = None
        # 尝试检查本地缓存是否已有 BGE-Reranker 模型
        local_model_path = os.getenv("BGE_RERANKER_PATH", "")
        if local_model_path and os.path.exists(local_model_path):
            try:
                from FlagEmbedding import FlagReranker
                self.reranker = FlagReranker(local_model_path, use_fp16=False)
                self.has_model = True
                print("✅ 成功加载本地 BGE-Reranker 深度重排模型！")
            except Exception as e:
                print(f"⚠️ 加载 BGE 模型失败，降级为规则打分: {e}")

    def rerank(self, query: str, candidates: List[Dict], top_n: int = 2) -> List[Dict]:
        """对候选文本精细打分排序，截取最相关的 top_n 条"""
        if not candidates:
            return []

        if self.has_model and self.reranker:
            try:
                # 构造 (Query, DocumentText) 对送入 Cross-Encoder
                pairs = [[query, doc["text"]] for doc in candidates]
                scores = self.reranker.compute_score(pairs)
                if isinstance(scores, (int, float)):
                    scores = [scores]
                # 绑定分数与文档
                scored_candidates = list(zip(candidates, scores))
                scored_candidates.sort(key=lambda x: x[1], reverse=True)
                return [doc for doc, _ in scored_candidates[:top_n]]
            except Exception as e:
                print(f"⚠️ Reranker 计算出错，使用原始顺序: {e}")
                return candidates[:top_n]

        # 【新手无 GPU 降级保护】：基于词频重合度做轻量级启发式精排
        print("💡 [Reranker] 采用轻量关键词交叉精排打分中...")
        # 先分词再比对，避免单字符集合匹配（如 delete 被拆成 d/e/l/t）造成无关文档误命中
        query_words = set(jieba.cut(query))
        scored = []
        for doc in candidates:
            overlap = sum(1 for w in query_words if w in doc["text"])
            scored.append((doc, overlap))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in scored[:top_n]]