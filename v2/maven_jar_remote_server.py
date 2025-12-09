#!/usr/bin/env python3
"""
Maven Jar 分析远程服务端
提供HTTP REST API接口供MCP Server调用
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import uvicorn
import logging
import tempfile
import shutil
import os

from maven_jar_analyzer import MavenJarAnalyzer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("maven-jar-remote-server")

# 创建FastAPI应用
app = FastAPI(
    title="Maven Jar Analyzer Service",
    description="远程Maven依赖分析和类反编译服务",
    version="1.0.0"
)

# 全局分析器实例
analyzer = MavenJarAnalyzer()


# ==================== 数据模型 ====================

class MavenDependency(BaseModel):
    """Maven依赖"""
    groupId: str
    artifactId: str
    version: str


class MavenRepository(BaseModel):
    """Maven仓库配置"""
    id: str
    name: str
    url: str
    snapshots: str = "true"


class AnalyzeDependencyRequest(BaseModel):
    """分析依赖请求"""
    dependencies: List[MavenDependency]
    target_classes: List[str]
    repositories: Optional[List[MavenRepository]] = None
    work_dir: Optional[str] = None


class DecompileClassRequest(BaseModel):
    """反编译类请求"""
    jar_path: str
    class_file_path: str


class FindAndDecompileRequest(BaseModel):
    """查找并反编译请求（一站式）"""
    dependencies: List[MavenDependency]
    target_classes: List[str]
    repositories: Optional[List[MavenRepository]] = None


# ==================== API端点 ====================

@app.get("/")
async def root():
    """健康检查"""
    return {
        "service": "Maven Jar Analyzer",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy"}


@app.post("/api/analyze")
async def analyze_dependency(request: AnalyzeDependencyRequest) -> Dict[str, Any]:
    """
    分析Maven依赖并查找指定的类
    
    Args:
        request: 分析依赖请求
        
    Returns:
        分析结果，包含找到的类信息和jar包列表
    """
    logger.info(f"Received analyze request for {len(request.dependencies)} dependencies")
    
    # 创建临时工作目录（如果未指定）
    work_dir = request.work_dir
    temp_dir_created = False
    
    if not work_dir:
        work_dir = tempfile.mkdtemp(prefix="maven_analyze_")
        temp_dir_created = True
        logger.info(f"Created temp work dir: {work_dir}")
    else:
        os.makedirs(work_dir, exist_ok=True)
    
    try:
        # 转换依赖格式
        dependencies = [dep.dict() for dep in request.dependencies]
        repositories = [repo.dict() for repo in request.repositories] if request.repositories else None
        
        # 创建pom.xml
        logger.info("Creating pom.xml")
        pom_path = analyzer.create_temp_pom(dependencies, work_dir, repositories)
        
        # 下载依赖
        logger.info("Downloading dependencies")
        jar_files = analyzer.download_dependencies(pom_path, work_dir)
        
        if not jar_files:
            raise HTTPException(status_code=404, detail="No jar files downloaded")
        
        logger.info(f"Downloaded {len(jar_files)} jar files")
        
        # 查找目标类
        logger.info(f"Searching for {len(request.target_classes)} target classes")
        found_classes = analyzer.find_exact_class_in_jars(jar_files, request.target_classes)
        
        # 构建返回结果
        result = {
            "found_classes": found_classes,
            "jar_files": jar_files,
            "work_dir": work_dir,
            "temp_dir": temp_dir_created
        }
        
        logger.info(f"Analysis complete: found {len(found_classes)} classes")
        return result
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        # 如果是临时目录，清理它
        if temp_dir_created and os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/decompile")
async def decompile_class(request: DecompileClassRequest) -> Dict[str, Any]:
    """
    反编译指定的类
    
    Args:
        request: 反编译请求
        
    Returns:
        反编译结果
    """
    logger.info(f"Decompiling {request.class_file_path} from {request.jar_path}")
    
    try:
        if not os.path.exists(request.jar_path):
            raise HTTPException(status_code=404, detail=f"Jar file not found: {request.jar_path}")
        
        # 反编译
        decompiled_code = analyzer.decompile_class(request.jar_path, request.class_file_path)
        
        # 提取类名
        class_name = request.class_file_path.replace('/', '.').replace('.class', '')
        
        result = {
            "class_name": class_name,
            "jar_path": request.jar_path,
            "class_file_path": request.class_file_path,
            "decompiled_code": decompiled_code
        }
        
        logger.info(f"Decompilation complete for {class_name}")
        return result
        
    except Exception as e:
        logger.error(f"Decompilation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/find-and-decompile")
async def find_and_decompile(request: FindAndDecompileRequest) -> Dict[str, Any]:
    """
    一站式服务：查找并反编译类
    
    Args:
        request: 查找并反编译请求
        
    Returns:
        包含分析和反编译结果
    """
    logger.info(f"Find and decompile request for {len(request.target_classes)} classes")
    
    # 先执行依赖分析
    analyze_request = AnalyzeDependencyRequest(
        dependencies=request.dependencies,
        target_classes=request.target_classes,
        repositories=request.repositories
    )
    
    analyze_result = await analyze_dependency(analyze_request)
    
    # 反编译所有找到的类
    decompiled_classes = {}
    found_classes = analyze_result.get("found_classes", {})
    
    for class_name, class_list in found_classes.items():
        if class_list:
            cls_info = class_list[0]  # 取第一个匹配
            logger.info(f"Decompiling {class_name}...")
            
            try:
                decompiled_code = analyzer.decompile_class(
                    cls_info["jar_path"],
                    cls_info["file_path"]
                )
                decompiled_classes[class_name] = decompiled_code
            except Exception as e:
                logger.error(f"Failed to decompile {class_name}: {e}")
                decompiled_classes[class_name] = f"Error: {str(e)}"
    
    # 合并结果
    result = {
        **analyze_result,
        "decompiled_classes": decompiled_classes
    }
    
    logger.info(f"Find and decompile complete: {len(decompiled_classes)} classes decompiled")
    return result


@app.delete("/api/cleanup/{work_dir:path}")
async def cleanup_work_dir(work_dir: str) -> Dict[str, str]:
    """
    清理工作目录
    
    Args:
        work_dir: 要清理的工作目录路径
        
    Returns:
        清理状态
    """
    logger.info(f"Cleaning up work directory: {work_dir}")
    
    try:
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)
            logger.info(f"Work directory cleaned: {work_dir}")
            return {"status": "success", "message": f"Cleaned up {work_dir}"}
        else:
            return {"status": "not_found", "message": f"Directory not found: {work_dir}"}
            
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 主函数 ====================

def main():
    """启动服务器"""
    logger.info("Starting Maven Jar Analyzer Remote Server...")
    
    # 配置
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8000"))
    
    logger.info(f"Server will listen on {host}:{port}")
    
    # 启动服务器
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
