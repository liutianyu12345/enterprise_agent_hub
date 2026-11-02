# BM25 + 向量检索 + RRF
"""
混合检索模块：结合 BM25（稀疏检索，擅长精确匹配函数名/错误码）与 稠密向量（语义匹配）
并通过 RRF（倒数排名融合）将两路候选打分归一合并。
"""
import jieba
from typing import List, Dict, Tuple
from rank_bm25 import BM25Okapi

# 1. 模拟企业内部技术资产与标准规约库
ENTERPRISE_KNOWLEDGE_BASE = [
    {
        "id": "doc_1",
        "title": "生产数据库更新规范",
        "text": "在生产环境中执行数据库变更时，严禁使用原生 delete 语句；必须使用软删除标志位 is_deleted=1，并在变更前备份数据。"
    },
    {
        "id": "doc_2",
        "title": "Python SDK 安全沙箱执行规范",
        "text": "自动化执行 Python 脚本必须使用 subprocess 隔离在临时命名沙箱中执行，设置硬超时时间为 5 秒，防止死循环耗尽 CPU。"
    },
    {
        "id": "doc_3",
        "title": "高危动作发布审批红线",
        "text": "凡是涉及数据库删除、服务器重启、向外部账户大额划款的操作，系统必须触发 interrupt_before 挂起图，强制等待二级审批。"
    },
    {
        "id": "doc_4",
        "title": "Go 网关高并发长连接最佳实践",
        "text": "Go 网关基于 Gin 框架开发，采用 Goroutine 与 http.Flusher 实现高并发 SSE 推流，并通过 c.Request.Context().Done() 检测断开。"
    },
    {
        "id": "doc_5",
        "title": "Reflexion 自动修复自愈模式",
        "text": "当沙箱测试执行失败时，将报错的 Traceback 包装为 Observation 提示词，注入 LLM 重试环路，上限设置为 3 次重试以防死循环。"
    }
]

class HybridRetriever:
    """混合检索器：BM25 + 向量检索 + RRF 融合"""

    def __init__(self, docs: List[Dict] = None):
        self.docs = docs if docs is not None else ENTERPRISE_KNOWLEDGE_BASE
        # 对文档分词建立 BM25 稀疏索引
        self.tokenized_corpus = [list(jieba.cut(d["text"])) for d in self.docs]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

    def bm25_search(self, query: str, top_k: int = 3) -> List[Tuple[Dict, float]]:
        """1. 稀疏检索：利用结巴分词计算 BM25 得分，精准捕获专有名词"""
        query_tokens = list(jieba.cut(query))
        scores = self.bm25.get_scores(query_tokens)
        # 按得分从大到小排序
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [(self.docs[i], float(scores[i])) for i in ranked_indices]

    def dense_search(self, query: str, top_k: int = 3) -> List[Tuple[Dict, float]]:
        """2. 稠密语义检索：实际生产对接 Qdrant，这里基于语义打分模拟召回"""
        # 演示环境根据语义关键词进行模拟，如含'审批'/'危险'优先返回 doc_3 和 doc_1
        simulated_rank = sorted(
            self.docs,
            key=lambda d: any(w in d["text"] for w in ["审批", "高危", "规范", "沙箱"]),
            reverse=True
        )
        return [(doc, 0.95 - idx * 0.1) for idx, doc in enumerate(simulated_rank[:top_k])]

    @staticmethod
    def rrf_fusion(
        dense_results: List[Tuple[Dict, float]],
        sparse_results: List[Tuple[Dict, float]],
        k: int = 60,
        top_n: int = 3
    ) -> List[Dict]:
        """
        3. RRF (Reciprocal Rank Fusion) 倒数排名融合算法
        公式: Score = sum( 1 / (k + rank) )
        解释：
          无论稀疏得分是 100 还是向量余弦相似度是 0.8，直接相加会因量纲不同而失真。
          RRF 只看候选文档在各个检索分支中的“相对排名 (Rank)”，平权倒数累加，兼顾两路优势！
          参数 k 常用 60，避免第 1 名的分数绝对统治后续排名。
        """
        rrf_scores = {}
        doc_store = {}

        # 累加向量路排名贡献
        for rank, (doc, _) in enumerate(dense_results, start=1):
            d_id = doc["id"]
            doc_store[d_id] = doc
            rrf_scores[d_id] = rrf_scores.get(d_id, 0.0) + (1.0 / (k + rank))

        # 累加 BM25 路排名贡献
        for rank, (doc, _) in enumerate(sparse_results, start=1):
            d_id = doc["id"]
            doc_store[d_id] = doc
            rrf_scores[d_id] = rrf_scores.get(d_id, 0.0) + (1.0 / (k + rank))

        # 按照融合打分降序排序
        sorted_docs = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
        return [doc_store[d_id] for d_id, _ in sorted_docs[:top_n]]

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict]:
        """对外统一检索入口"""
        sparse_res = self.bm25_search(query, top_k=top_k)
        dense_res = self.dense_search(query, top_k=top_k)
        fused = self.rrf_fusion(dense_res, sparse_res, k=60, top_n=top_k)
        return fused