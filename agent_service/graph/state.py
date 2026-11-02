# TypedDict 状态定义
"""
LangGraph 核心理念：将全生命周期数据集中在一个强类型 TypedDict 中。
每一个 Node（节点）都是纯函数，输入 State，输出对 State 的字段增量修改。
"""
from typing import TypedDict, Optional

class AgentState(TypedDict):
    task: str                 # 用户提出的原始开发/运维需求（例如："写一段脚本清理日志"）
    thread_id: str            # 唯一的会话上下文 ID，用于 Checkpoint 恢复与多轮追踪
    rag_context: str          # 进阶 RAG 检索到的技术文档片段
    code: str                 # 模型当前生成的 Python 代码
    error_message: str        # 沙箱执行后捕获的 stderr 报错堆栈
    retry_count: int          # 当前已重试自愈的次数（最大设为 3，防止死循环）
    is_dangerous: bool        # 是否涉及高危敏感操作（如删除/清库）
    approved: bool            # 人工审批标志位：True 为已批准，False 为未批准
    status: str               # 任务流转状态: "PROCESSING", "WAITING_APPROVAL", "COMPLETED", "FAILED",分别是处理中、等待审批、已完成、已失败状态
    final_output: str         # 最终返回给用户的执行结论/日志