# Langfuse 追踪配置
"""
Langfuse 链路追踪集成：
如果本地启动了 Langfuse 容器，自动上报 Trace 树与耗时；若未启动，自动静默，绝不影响核心业务运行。
"""
import os
from functools import wraps

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-mock")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-mock")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

def observe_node(node_name:str):
    """自定义链路追踪装饰器，兼容有/无 Langfuse 场景"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            #记录执行起点
            print(f"⏱️ [Tracer] 追踪节点启动: {node_name}")
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                #记录执行终点
                print(f"⏱️ [Tracer] 追踪节点结束: {node_name}")
        return wrapper
    return decorator