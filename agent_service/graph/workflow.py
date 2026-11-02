# LangGraph 状态图构建与编译

"""
LangGraph 状态图组装：
1. add_node 添加算子
2. add_edge 添加固定连线
3. add_conditional_edges 条件分支路由
4. compile 编译并注入 MemorySaver 快照与 interrupt_before 挂起点
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Checkpointer
from torch.utils import checkpoint
from agent_service.graph.state import AgentState
from agent_service.graph.nodes import (
    rag_node,
    coder_node,
    sandbox_node,
    reflect_node,
    danger_check_node,
    approval_node,
    fallback_node
)

def route_after_sandbox(state: AgentState) -> str:
    """沙箱运行后的条件路由函数"""
    # 1. 如果有报错，说明需要自愈
    if state.get("error_message"):
        if state.get("retry_count",0) >= 3:
            return "to_fallback" # 3次重试后，跳转到 fallback 节点
        return "to_reflect"       # 否则进入反思自愈环路
    # 2. 运行成功，检查是否涉及高危敏感操作
    return "to_danger_check"
def route_after_danger(state: AgentState) -> str:
    """高危检测后的条件路由函数"""
    if state.get("is_dangerous"):
        return "to_approval"      # 涉及高危，路由到需要人工审批的节点
    return "to_end"               # 普通安全操作，直接顺利完结
def build_hub_graph():
    """构建企业级自愈与人工在环状态图"""
    workflow = StateGraph(AgentState)
    # 1.注册全部运算节点
    workflow.add_node("rag", rag_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("sandbox", sandbox_node)
    workflow.add_node("reflect", reflect_node)
    workflow.add_node("danger_check", danger_check_node)    
    workflow.add_node("approval", approval_node)
    workflow.add_node("fallback", fallback_node)
    #2. 设置图的唯一起始入口节点
    workflow.set_entry_point("rag")
    #3. 编排边与数据流转
    workflow.add_edge("rag", "coder")
    workflow.add_edge("coder", "sandbox")
    #条件分支A:沙箱执行后
    workflow.add_conditional_edges("sandbox", route_after_sandbox,
    {
        "to_fallback": "fallback",
        "to_reflect": "reflect",
        "to_danger_check": "danger_check",
    }
    )
    #环路闭环！反思节点指向Coder节点重新编写代码
    workflow.add_edge("reflect", "coder")
    #条件分支B:高危检测后
    workflow.add_conditional_edges("danger_check", route_after_danger,
    {
        "to_approval": "approval",
        "to_end": END,
    }
    )
    workflow.add_edge("approval", END)
    workflow.add_edge("fallback", END)
    #4. 配置Checkpointer快照持久化机制
    # 生产环境中推荐替换为 PostgresSaver 实现跨进程/跨机器恢复；本地使用 MemorySaver
    checkpointer = MemorySaver()
    # 5. 编译状态图：核心在高危 approval 节点前挂起！
    app = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["approval"], # 挂起点：高危审批节点前
    )
    return app
# 全局单例编译图
hub_graph = build_hub_graph()

    
