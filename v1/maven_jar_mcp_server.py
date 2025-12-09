#!/usr/bin/env python3
"""
Maven Jar Analyzer MCP Server
提供Maven依赖分析和类反编译的MCP服务
"""

import asyncio
import json
import logging
import sys
from typing import Any, Optional, List, Dict

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError as e:
    print(f"错误: 缺少MCP依赖包。请运行: pip install mcp", file=sys.stderr)
    sys.exit(1)

from maven_jar_analyzer import MavenJarAnalyzer

# 配置日志 - 输出到stderr避免干扰stdio通信
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("maven-jar-mcp")

# 创建MCP服务器实例
app = Server("maven-jar-analyzer")

# 全局分析器实例
analyzer = MavenJarAnalyzer()


@app.list_tools()
async def list_tools() -> list[Tool]:
    """列出所有可用的工具"""
    return [
        Tool(
            name="analyze_maven_dependency",
            description="""分析Maven依赖并查找指定的类。
            
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
                        "description": "工作目录路径（可选，默认使用./maven_temp）"
                    }
                },
                "required": ["dependencies", "target_classes"]
            }
        ),
        Tool(
            name="decompile_class",
            description="""反编译指定的类，返回字节码或源代码。

参数说明：
- jar_path: jar包的完整路径
- class_file_path: 类在jar包中的路径（如 com/example/MyClass.class）

返回格式：
{
    "class_name": "类名",
    "decompiled_code": "反编译后的代码内容"
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
                        "description": "类在jar包中的路径（如 com/example/MyClass.class）"
                    }
                },
                "required": ["jar_path", "class_file_path"]
            }
        ),
        Tool(
            name="find_and_decompile_classes",
            description="""一站式服务：分析Maven依赖、查找类并反编译所有找到的类。

这是一个组合工具，集成了 analyze_maven_dependency 和 decompile_class 的功能。

参数说明：同 analyze_maven_dependency

返回格式：
{
    "found_classes": {...},
    "decompiled_classes": {
        "ClassName": "反编译后的代码"
    },
    "jar_files": [...],
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
                    },
                    "work_dir": {
                        "type": "string",
                        "description": "工作目录路径（可选）"
                    }
                },
                "required": ["dependencies", "target_classes"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """处理工具调用"""
    try:
        if name == "analyze_maven_dependency":
            return await handle_analyze_dependency(arguments)
        elif name == "decompile_class":
            return await handle_decompile_class(arguments)
        elif name == "find_and_decompile_classes":
            return await handle_find_and_decompile(arguments)
        else:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown tool: {name}"})
            )]
    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}", exc_info=True)
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)})
        )]


async def handle_analyze_dependency(arguments: Dict[str, Any]) -> list[TextContent]:
    """处理依赖分析请求"""
    import os
    import tempfile
    
    dependencies = arguments.get("dependencies", [])
    target_classes = arguments.get("target_classes", [])
    repositories = arguments.get("repositories")
    work_dir = arguments.get("work_dir", "./maven_temp")
    
    logger.info(f"Analyzing dependencies: {dependencies}")
    logger.info(f"Target classes: {target_classes}")
    
    # 创建工作目录
    os.makedirs(work_dir, exist_ok=True)
    
    # 创建pom.xml
    pom_path = analyzer.create_temp_pom(dependencies, work_dir, repositories)
    
    # 下载依赖
    jar_files = analyzer.download_dependencies(pom_path, work_dir)
    
    # 查找类
    found_classes = analyzer.find_exact_class_in_jars(jar_files, target_classes)
    
    # 构建结果
    result = {
        "found_classes": {
            class_name: [
                {
                    "class_name": cls_info["class_name"],
                    "jar_path": cls_info["jar_path"],
                    "file_path": cls_info["file_path"]
                }
                for cls_info in class_list
            ]
            for class_name, class_list in found_classes.items()
        },
        "jar_files": jar_files,
        "work_dir": work_dir,
        "summary": {
            "total_jars": len(jar_files),
            "found_classes_count": len(found_classes),
            "missing_classes": [cls for cls in target_classes if cls not in found_classes]
        }
    }
    
    return [TextContent(
        type="text",
        text=json.dumps(result, indent=2, ensure_ascii=False)
    )]


async def handle_decompile_class(arguments: Dict[str, Any]) -> list[TextContent]:
    """处理类反编译请求"""
    jar_path = arguments.get("jar_path")
    class_file_path = arguments.get("class_file_path")
    
    if not jar_path or not class_file_path:
        return [TextContent(
            type="text",
            text=json.dumps({"error": "jar_path and class_file_path are required"})
        )]
    
    logger.info(f"Decompiling {class_file_path} from {jar_path}")
    
    # 反编译
    decompiled_code = analyzer.decompile_class(jar_path, class_file_path)
    
    # 提取类名
    class_name = class_file_path.replace('/', '.').replace('.class', '')
    
    result = {
        "class_name": class_name,
        "jar_path": jar_path,
        "class_file_path": class_file_path,
        "decompiled_code": decompiled_code
    }
    
    return [TextContent(
        type="text",
        text=json.dumps(result, indent=2, ensure_ascii=False)
    )]


async def handle_find_and_decompile(arguments: Dict[str, Any]) -> list[TextContent]:
    """处理查找并反编译请求（一站式服务）"""
    # 先执行依赖分析
    analyze_result = await handle_analyze_dependency(arguments)
    analyze_data = json.loads(analyze_result[0].text)
    
    if "error" in analyze_data:
        return analyze_result
    
    # 反编译所有找到的类
    decompiled_classes = {}
    found_classes = analyze_data.get("found_classes", {})
    
    for class_name, class_list in found_classes.items():
        if class_list:
            cls_info = class_list[0]  # 取第一个匹配
            logger.info(f"Decompiling {class_name}...")
            
            decompiled_code = analyzer.decompile_class(
                cls_info["jar_path"],
                cls_info["file_path"]
            )
            
            decompiled_classes[class_name] = decompiled_code
    
    # 合并结果
    result = {
        **analyze_data,
        "decompiled_classes": decompiled_classes
    }
    
    return [TextContent(
        type="text",
        text=json.dumps(result, indent=2, ensure_ascii=False)
    )]


async def main():
    """启动MCP服务器"""
    logger.info("Starting Maven Jar Analyzer MCP Server...")
    
    try:
        # 使用stdio_server作为上下文管理器
        async with stdio_server() as (read_stream, write_stream):
            logger.info("Server initialized, ready to accept connections")
            
            # 运行服务器
            init_options = app.create_initialization_options()
            await app.run(
                read_stream,
                write_stream,
                init_options
            )
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


def run_server():
    """同步入口函数"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run_server()
