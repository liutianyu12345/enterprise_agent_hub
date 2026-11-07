# 节点实现 (Coder, Sandbox, Reflect)
"""
节点逻辑定义：
1. rag_node: 混合检索知识库
2. coder_node: 调用大模型编写/修复代码
3. sandbox_node: 沙箱子进程执行隔离代码
4. reflect_node: 错误反思并累加重试计数器
5. danger_check_node: 检测高危敏感动作
6. fallback_node: 超过重试上限时的熔断兜底
7. approval_node: 人工批准后的执行节点
"""

import os
import subprocess
import tempfile
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from agent_service.rag.hybrid_retriever import HybridRetriever
from agent_service.rag.reranker import DocumentReranker
from agent_service.graph.state import AgentState

#初始化检索器与重排序器
retriever = HybridRetriever()
reranker = DocumentReranker()

def get_llm():
    """获取大模型实例（优先使用环境变量，支持 DeepSeek、OpenAI、vLLM）"""
    return ChatOpenAI(
        model=os.getenv("MODEL_NAME", "deepseek-chat"),
        api_key=os.getenv("DEEPSEEK_API_KEY", "mock-key"),
        base_url=os.getenv("BASE_URL", "https://api.deepseek.com"),
        temperature=0.2, # 编写代码采用低随机性
    )
def rag_node(state: AgentState) ->dict:
    """节点 1：检索与当前任务相关的企业规约与规范"""
    task = state["task"]
    print(f"\n📚 [Node: RAG] 正在检索企业内部规约...")
    cadidates = retriever.retrieve(task,top_k=3)
    top_docs = reranker.rerank(task,cadidates,top_n=2)
    context_str =  "\n".join([f"【规范{i+1}】{d['title']}: {d['text']}" for i, d in enumerate(top_docs)])
    return {"rag_context": context_str,"status":"PROCESSING"}
def coder_node(state: AgentState) ->dict:
    """节点 2：调用大模型编写/修复代码(Reflexion关键:若有 error_message，则触发带错反思修复)"""
    retry = state.get("retry_count",0)
    print(f"\n🚀 [Node: Coder] 正在调用大模型编写代码，第 {retry+1} 次尝试...")
    llm = get_llm()
     # 判断是否处于 Reflexion 自愈循环中
    if state.get("error_message"):
        system_prompt = "你是一位高级资深研发专家。你之前编写的代码在沙箱测试中发生了报错，请根据错误堆栈进行深度反思，并输出修复后的可独立执行的纯 Python 代码。"
        user_prompt = f"""【需求】：{state['task']}
【企业技术规约】：
{state.get('rag_context', '')}

【上一次执行报错堆栈】：
{state['error_message']}

【有问题的原代码】：
{state['code']}

请针对上述错误进行精准修复。注意：只输出修复后的纯 Python 代码，绝对不要包含 ```python 或 ``` 等 Markdown 标记，不要有任何多余文字说明！"""
    else:
        system_prompt = "你是一位高级资深研发专家，擅长编写健壮的 Python 脚本。请遵循内部技术规约生成符合需求的代码。"
        user_prompt = f"""【需求】：{state['task']}
【企业技术规约参考】：
{state.get('rag_context', '')}

请编写一段完整、自包含且带 print 输出验证的纯 Python 代码。
注意：直接输出纯 Python 代码，严禁包含任何 Markdown 语法（如 ```python ）。"""
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        raw_code = response.content.replace("```python", "").replace("```", "").strip()
    except Exception as e:
        # 无 API Key 时的离线兜底代码，方便新手无需充值直接体验全流程
        print(f"⚠️ [Coder] 调用大模型失败 ({e})，使用内置演示代码演示自愈流程...")
        if retry == 0:
            # 第一次故意给一个有 bug 的代码：未定义变量引发 NameError
            raw_code = "print('正在尝试执行...'); res = undefined_variable + 1; print(res)"
        else:
            # 第二次给已修复的代码
            raw_code = "print('>>> 自愈修复成功！执行安全业务逻辑完成。')"

    return {"code": raw_code}
def sandbox_node(state: AgentState) ->dict:
    """节点 3：代码沙箱执行测试（通过独立临时文件与 subprocess 隔离开）"""
    print(f"\n🚀 [Node: Sandbox] 正在沙箱测试代码...")
    code = state["code"]
    # 创建命名临时文件
    with tempfile.NamedTemporaryFile("w",suffix = ".py",delete = False,encoding="utf-8") as f:
        f.write(code)
        temp_file_path = f.name
    try:
        #硬超时5秒，防止恶意火死循环代码堵死线程池
        res = subprocess.run(
            ["python", temp_file_path],
            timeout=5,
            capture_output=True,
            text = True,
            encoding="utf-8"
        )
        # Windows 下子进程没有任何输出时，communicate() 返回的 stdout/stderr 为 None，不能直接 strip
        stdout = (res.stdout or "").strip()
        stderr = (res.stderr or "").strip()
        if res.returncode == 0:
            print(f"✅ [Sandbox] 运行通过！标准输出:\n{stdout}")
            return {
                "error_message": "",
                "final_output": stdout
            }
        else:
            #捕获真实stderr 报错信息；无 stderr 时退化为 stdout 或退出码，避免被判为执行成功
            err_msg = stderr or stdout or f"ExecutionError: 进程异常退出（退出码 {res.returncode}），无输出信息"
            print(f"❌ [Sandbox] 运行报错:\n{err_msg}")
            return {"error_message": err_msg}
    except subprocess.TimeoutExpired:
        return {"error_message": "ExecutionError: 代码执行超过 5 秒硬超时限制！可能存在死循环！"}
    except Exception as e:
        return {"error_message": f"ExecutionError: 沙箱环境异常: {str(e)}"}
    finally:
        #无论成功失败，必须安全清理临时脚本文件
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
def reflect_node(state: AgentState) ->dict:
    """节点 4：Reflexion 反思节点，累加重试计数器"""
    next_retry = state.get("retry_count",0) + 1
    print(f"🔄 [Node: Reflexion] 捕获错误堆栈，推进自愈闭环 (即将进入第 {next_retry} 次重试)...")
    return {"retry_count": next_retry}
def danger_check_node(state: AgentState) ->dict:
    """节点 5：危险检查节点，判断代码是否包含危险操作（如删除文件、修改系统配置等）"""
    code = state.get("code","")
    task = state.get("task","")
    # 高危关键词列表
    dangerous_keywords = ["delete", "drop", "rmdir", "remove", "kill", "reboot", "shutdown", "format"]
    is_danger = any(kw in code.lower() or kw in task.lower() for kw in dangerous_keywords)
    if is_danger:
        print("🚨 [Node: DangerCheck] 警报：检测到包含高危敏感操作（删库/删文件/关机）！需挂起审批！")
        return {"is_dangerous": True, "status": "WAITING_APPROVAL"}
    
    return {"is_dangerous": False, "status": "COMPLETED"}
def approval_node(state: AgentState) -> dict:
    """节点 6：人工审批节点（被 interrupt_before 挂起点，只有人工确认恢复后才会走进来）"""
    print("🎉 [Node: Approval] 人工确认审批通过！高危脚本已授信执行。")
    return {
        "approved": True,
        "status": "COMPLETED",
        "final_output": state.get("final_output", "") + "\n[生产操作已获安全委员会人工批准，正式生效]"
    }
def fallback_node(state: AgentState) -> dict:
    """节点 7：重试达到上限后的熔断降级兜底节点"""
    print("🛑 [Node: Fallback] 已达到最大重试上限 3 次，自愈失败！触发服务熔断降级！")
    return {
        "status": "FAILED",
        "final_output": f"任务执行失败：历经 3 轮自愈仍未修复代码错误。\n最后错误记录:\n{state.get('error_message')}"
    }
