"""FastAPI 服务入口：暴露流式接口与人工审批恢复接口"""
import json
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from agent_service.graph.workflow import hub_graph

app = FastAPI(title="Enterprise Agent Hub Core Service", version="1.0.0")

class StreamRequest(BaseModel):
    prompt: str
    thread_id: str = "session_default"

class ApproveRequest(BaseModel):
    thread_id: str
    approved: bool
#健康检查接口
@app.get("/health")
def health_check():
    return {"status": "ok", "server":"Python Agent Service"}
#流式执行接口
@app.post("/stream")
async def stream_task(req: StreamRequest):
    """流式执行 Agent 图任务"""
    config  = {"configurable" : {"thread_id": req.thread_id}}

    initial_state ={
        "task": req.prompt,
        "thread_id": req.thread_id,
        "rag_context": "",
        "code": "",
        "error_message": "",
        "retry_count": 0,
        "is_dangerous": False,
        "approved": False,
        "status": "PROCESSING",
        "final_output": ""
    }
    async def event_generator():
        print(f"🚀 开始流式执行任务: [Thread: {req.thread_id}] Prompt: {req.prompt}")
        # 使用 hub_graph.stream 遍历图的每个节点产生的状态更新
        for event in hub_graph.stream(initial_state, config=config):
            for node_name,node_update in event.items():
                payload = {
                    "node": node_name,
                    "status": node_update("status", "PROCESSING"),
                    "code": node_update("code", ""),
                    "error": node_update("error_message", ""),
                    "retry_count": node_update("retry_count", 0),
                    "output": node_update("final_output", "")
                }
                #发送 SSE 数据行
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.5) #微延时，平滑打字效果
            #检查是否遇到了 interrupt_before 挂起点
            current_state = hub_graph.get_state(config)
            if current_state.next and "approval" in current_state.next:
                interrupt_payload = {
                    "node": "INTERRUPT",
                    "status": "WAITING_APPROVAL",
                    "output": "⚠️ 涉及高危敏感操作，流程已安全挂起，等待主管人工点击审批！",
                    "code": current_state.values.get("code", "")
                }
                yield f"data: {json.dumps(interrupt_payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(event_generator(),media_type="text/event-stream")

@app.post("/approve")
async def approve_task(req: ApproveRequest):
    """人工审批恢复恢复任务"""
    config = {"configurable" : {"thread_id": req.thread_id}}
    print(f"人工审批恢复任务: [Thread: {req.thread_id}] Approved: {req.approved}")
    async def resume_generator():
        if not req.approved:
            #人工审批拒绝
            hub_graph.update_state(config, {"status": "REJECTED","final_output":"人工审批拒绝，任务已终止"})
            yield f"data: {json.dumps({'status': 'REJECTED', 'message': '任务已被人工驳回！'})}\n\n"
            yield "data: [DONE]\n\n"
            return
        # 人工同意执行：传入 None，从 Checkpointer 快照断点无缝恢复
        for event in hub_graph.stream(None, config=config):
            for node_name,node_update in event.items():
                payload = {
                    "node": node_name,
                    "status": node_update.get("status", "COMPLETED"),
                    "output": node_update.get("final_output", "")
                }

                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.5) #微延时，平滑打字效果
        yield "data: [DONE]\n\n"
    return StreamingResponse(resume_generator(),media_type="text/event-stream")
if __name__ == "__main__":
    import uvicorn
    # 本地启动于 8000 端口
    uvicorn.run("agent_service.server:app", host="0.0.0.0", port=8000, reload=False)


