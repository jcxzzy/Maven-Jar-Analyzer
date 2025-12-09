#!/usr/bin/env python3
"""
Maven Jar Analyzer MCP Server (转发层 - HTTP/SSE版本)
作为MCP协议服务器,通过HTTP和SSE与客户端通信,将请求转发到远程HTTP服务端
支持 MCP streamable-http 协议规范
"""

import asyncio
import json
import logging
import sys
import os
from typing import Any, Optional, List, Dict
import httpx
from fastapi import FastAPI, Request, Header
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import uvicorn

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
except ImportError as e:
    print(f"错误: 缺少MCP依赖包。请运行: pip install mcp fastapi sse-starlette uvicorn", file=sys.stderr)
    sys.exit(1)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("maven-jar-mcp-proxy-http")

# 创建FastAPI应用
fastapi_app = FastAPI(
    title="Maven Jar Analyzer MCP Proxy (Streamable HTTP)",
    description="MCP协议代理服务器，支持streamable-http传输协议",
    version="2.0.0"
)

# 添加CORS中间件
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有源，生产环境建议限制具体域名
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有请求头
)

# 创建MCP服务器实例
mcp_server = Server("maven-jar-analyzer-proxy")

# 远程服务端配置
REMOTE_SERVER_URL = os.getenv("REMOTE_SERVER_URL", "http://localhost:8000")
logger.info(f"Remote server URL: {REMOTE_SERVER_URL}")

# HTTP客户端配置
HTTP_TIMEOUT = 300.0  # 5分钟超时（Maven下载可能很慢）

@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """列出所有可用的工具"""
    return [
        Tool(
            name="analyze_maven_dependency",
            description="""分析Maven依赖并查找指定的类（通过远程服务端）。

功能：
1. 根据Maven坐标下载jar包及其依赖
2. 在下载的jar包中搜索指定的类
3. 返回找到的类的基本信息

参数说明：
- dependencies: Maven依赖列表，每个依赖包含 groupId, artifactId, version
- target_classes: 要查找的类名列表（支持简单类名）
- repositories: 可选的Maven仓库配置（用于私有仓库或SNAPSHOT版本）
- work_dir: 可选的工作目录路径（默认使用临时目录）

返回格式：
{
    "found_classes": {
        "ClassName": [{
            "class_name": "完整类名",
            "jar_path": "jar包路径",
            "file_path": "类在jar中的路径"
        }]
    },
    "jar_files": ["下载的jar包列表"],
    "work_dir": "工作目录路径"
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "dependencies": {
                        "type": "array",
                        "description": "Maven依赖列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "groupId": {"type": "string", "description": "Maven groupId"},
                                "artifactId": {"type": "string", "description": "Maven artifactId"},
                                "version": {"type": "string", "description": "版本号"}
                            },
                            "required": ["groupId", "artifactId", "version"]
                        }
                    },
                    "target_classes": {
                        "type": "array",
                        "description": "要查找的类名列表（简单类名即可）",
                        "items": {"type": "string"}
                    },
                    "repositories": {
                        "type": "array",
                        "description": "Maven仓库配置（可选）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "url": {"type": "string"},
                                "snapshots": {"type": "string", "default": "true"}
                            }
                        }
                    },
                    "work_dir": {
                        "type": "string",
                        "description": "工作目录路径（可选）"
                    }
                },
                "required": ["dependencies", "target_classes"]
            }
        ),
        
        Tool(
            name="decompile_class",
            description="""反编译指定jar包中的类（通过远程服务端）。

参数说明：
- jar_path: jar包的完整路径
- class_file_path: 类在jar中的相对路径（如 com/example/MyClass.class）

返回格式：
{
    "class_name": "完整类名",
    "jar_path": "jar包路径",
    "class_file_path": "类文件路径",
    "decompiled_code": "反编译后的代码"
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "jar_path": {
                        "type": "string",
                        "description": "jar包的完整路径"
                    },
                    "class_file_path": {
                        "type": "string",
                        "description": "类在jar中的相对路径"
                    }
                },
                "required": ["jar_path", "class_file_path"]
            }
        ),
        
        Tool(
            name="find_and_decompile",
            description="""一站式服务：查找依赖、定位类、反编译（通过远程服务端）。

这是最便捷的工具，一次调用完成所有操作。

参数说明：
- dependencies: Maven依赖列表
- target_classes: 要查找并反编译的类名列表
- repositories: 可选的Maven仓库配置

返回格式：
{
    "found_classes": {...},  // 找到的类信息
    "jar_files": [...],      // jar包列表
    "work_dir": "...",       // 工作目录
    "decompiled_classes": {  // 反编译结果
        "ClassName": "反编译代码..."
    }
}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "dependencies": {
                        "type": "array",
                        "description": "Maven依赖列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "groupId": {"type": "string"},
                                "artifactId": {"type": "string"},
                                "version": {"type": "string"}
                            },
                            "required": ["groupId", "artifactId", "version"]
                        }
                    },
                    "target_classes": {
                        "type": "array",
                        "description": "要查找并反编译的类名列表",
                        "items": {"type": "string"}
                    },
                    "repositories": {
                        "type": "array",
                        "description": "Maven仓库配置（可选）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "url": {"type": "string"},
                                "snapshots": {"type": "string"}
                            }
                        }
                    }
                },
                "required": ["dependencies", "target_classes"]
            }
        )
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """处理工具调用请求"""
    logger.info(f"Tool called: {name}")
    logger.debug(f"Arguments: {json.dumps(arguments, indent=2, ensure_ascii=False)}")
    
    try:
        if name == "analyze_maven_dependency":
            return await handle_analyze_dependency(arguments)
        elif name == "decompile_class":
            return await handle_decompile_class(arguments)
        elif name == "find_and_decompile":
            return await handle_find_and_decompile(arguments)
        else:
            logger.error(f"Unknown tool: {name}")
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown tool: {name}"})
            )]
    except Exception as e:
        logger.error(f"Tool execution error: {e}", exc_info=True)
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)})
        )]


async def handle_analyze_dependency(arguments: Dict[str, Any]) -> list[TextContent]:
    """处理依赖分析请求 - 转发到远程服务端"""
    logger.info("Forwarding analyze_dependency request to remote server")
    
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            response = await client.post(
                f"{REMOTE_SERVER_URL}/api/analyze",
                json=arguments
            )
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Remote server returned: {len(result.get('jar_files', []))} jars")
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Remote server error: {str(e)}",
                    "remote_url": REMOTE_SERVER_URL
                })
            )]


async def handle_decompile_class(arguments: Dict[str, Any]) -> list[TextContent]:
    """处理反编译请求 - 转发到远程服务端"""
    logger.info("Forwarding decompile_class request to remote server")
    
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            response = await client.post(
                f"{REMOTE_SERVER_URL}/api/decompile",
                json=arguments
            )
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Decompiled class: {result.get('class_name')}")
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Remote server error: {str(e)}",
                    "remote_url": REMOTE_SERVER_URL
                })
            )]


async def handle_find_and_decompile(arguments: Dict[str, Any]) -> list[TextContent]:
    """处理一站式请求 - 转发到远程服务端"""
    logger.info("Forwarding find_and_decompile request to remote server")
    
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            response = await client.post(
                f"{REMOTE_SERVER_URL}/api/find-and-decompile",
                json=arguments
            )
            response.raise_for_status()
            result = response.json()
            
            decompiled_count = len(result.get('decompiled_classes', {}))
            logger.info(f"Decompiled {decompiled_count} classes")
            
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False)
            )]
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Remote server error: {str(e)}",
                    "remote_url": REMOTE_SERVER_URL
                })
            )]


# ==================== FastAPI HTTP/SSE 端点 ====================

@fastapi_app.get("/")
async def root():
    """根路径 - MCP 服务器信息 (符合 Cursor streamable_http 规范)"""
    return {
        "name": "maven-jar-analyzer-proxy",
        "version": "2.0.0",
        "protocol_version": "2024-11-05",
        "capabilities": {
            "tools": True,
            "resources": False,
            "prompts": False,
            "sampling": False
        },
        "serverInfo": {
            "name": "Maven Jar Analyzer MCP Proxy",
            "version": "2.0.0"
        },
        "instructions": "MCP Server for Maven JAR Analysis via streamable-http"
    }

@fastapi_app.post("/")
async def root_post(request: Request):
    """根路径 POST - 处理 MCP JSON-RPC 请求 (Cursor streamable_http 必需)"""
    try:
        body = await request.json()
        method = body.get("method", "")
        request_id = body.get("id")
        
        logger.info(f"Received JSON-RPC request: method={method}, id={request_id}")
        
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {},
                    },
                    "serverInfo": {
                        "name": "maven-jar-analyzer-proxy",
                        "version": "2.0.0"
                    }
                }
            }
        elif method == "tools/list":
            tools = await list_tools()
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema
                        }
                        for tool in tools
                    ]
                }
            }
        elif method == "tools/call":
            params = body.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            logger.info(f"Calling tool: {tool_name} with arguments: {arguments}")
            
            if not tool_name:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Missing tool name in params"
                    }
                }
            
            result = await call_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": content.type,
                            "text": content.text
                        }
                        for content in result
                    ]
                }
            }
        elif method == "notifications/initialized":
            # 客户端初始化完成通知，不需要响应
            logger.info("Client initialized")
            return {"jsonrpc": "2.0"}
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }
    except Exception as e:
        logger.error(f"Root POST error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": request_id if "request_id" in locals() else None,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
        )


@fastapi_app.get("/health")
async def health_check():
    """健康检查端点"""
    # 检查远程服务器
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{REMOTE_SERVER_URL}/health")
            remote_healthy = response.status_code == 200
    except Exception:
        remote_healthy = False
    
    return {
        "status": "healthy" if remote_healthy else "degraded",
        "remote_server_healthy": remote_healthy,
        "remote_server_url": REMOTE_SERVER_URL
    }


# MCP Protocol 标准端点（兼容旧端点）
@fastapi_app.get("/mcp")
async def mcp_info():
    """MCP 服务器信息（兼容旧端点）"""
    return await root()


@fastapi_app.post("/mcp/tools/list")
async def mcp_list_tools():
    """MCP 列出工具（符合 streamable-http 规范）"""
    try:
        tools = await list_tools()
        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema
                }
                for tool in tools
            ]
        }
    except Exception as e:
        logger.error(f"List tools error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": -32603, "message": str(e)}}
        )


@fastapi_app.post("/mcp/tools/call")
async def mcp_call_tool(request: Request):
    """MCP 调用工具（符合 streamable-http 规范）"""
    try:
        body = await request.json()
        tool_name = body.get("name")
        arguments = body.get("arguments", {})
        
        if not tool_name:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": -32602,
                        "message": "Missing tool name"
                    }
                }
            )
        
        result = await call_tool(tool_name, arguments)
        
        # 转换 TextContent 为 MCP 格式
        return {
            "content": [
                {
                    "type": content.type,
                    "text": content.text
                }
                for content in result
            ],
            "isError": False
        }
    except Exception as e:
        logger.error(f"Call tool error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": -32603,
                    "message": str(e)
                },
                "isError": True
            }
        )


@fastapi_app.get("/mcp/sse")
async def mcp_sse_endpoint(request: Request):
    """MCP SSE端点（符合 streamable-http 规范）"""
    async def event_generator():
        try:
            # 发送初始化消息
            yield {
                "event": "endpoint",
                "data": json.dumps({
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {}
                })
            }
            
            # 保持连接，等待客户端断开
            while True:
                if await request.is_disconnected():
                    break
                await asyncio.sleep(30)
                # 发送心跳
                yield {
                    "event": "ping",
                    "data": json.dumps({"type": "ping"})
                }
        except asyncio.CancelledError:
            logger.info("SSE connection cancelled")
        except Exception as e:
            logger.error(f"SSE error: {e}", exc_info=True)
    
    return EventSourceResponse(event_generator())


# 兼容旧版本的端点（保持向后兼容）
@fastapi_app.post("/mcp/v1/tools/list")
async def http_list_tools():
    """HTTP方式列出工具（兼容旧版本）"""
    return await mcp_list_tools()


@fastapi_app.post("/mcp/v1/tools/call")
async def http_call_tool(request: Request):
    """HTTP方式调用工具（兼容旧版本）"""
    return await mcp_call_tool(request)


@fastapi_app.get("/sse")
async def sse_endpoint(request: Request):
    """SSE端点（兼容旧版本）"""
    return await mcp_sse_endpoint(request)


def main():
    """启动HTTP/SSE服务器"""
    logger.info("Starting Maven Jar Analyzer MCP Proxy Server (Streamable HTTP)...")
    logger.info(f"Forwarding requests to: {REMOTE_SERVER_URL}")
    
    # 配置
    host = os.getenv("PROXY_HOST", "0.0.0.0")
    port = int(os.getenv("PROXY_PORT", "8001"))
    
    logger.info(f"Server will listen on {host}:{port}")
    logger.info("=" * 70)
    logger.info("MCP Streamable HTTP Endpoints:")
    logger.info(f"  - GET  http://{host}:{port}/              (服务信息)")
    logger.info(f"  - GET  http://{host}:{port}/health        (健康检查)")
    logger.info(f"  - GET  http://{host}:{port}/mcp           (MCP信息)")
    logger.info(f"  - POST http://{host}:{port}/mcp/tools/list    (列出工具)")
    logger.info(f"  - POST http://{host}:{port}/mcp/tools/call    (调用工具)")
    logger.info(f"  - GET  http://{host}:{port}/mcp/sse           (SSE流)")
    logger.info("=" * 70)
    logger.info("\nCursor 配置示例:")
    logger.info(json.dumps({
        "mcpServers": {
            "maven-jar-analyzer": {
                "transport": {
                    "type": "streamable-http",
                    "url": f"http://{host if host != '0.0.0.0' else 'localhost'}:{port}"
                }
            }
        }
    }, indent=2))
    logger.info("=" * 70)
    
    # 启动服务器
    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
