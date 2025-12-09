# Maven Jar Analyzer MCP Service

Maven依赖分析和类反编译的MCP服务，支持远程调用。

## 功能特性

✅ **Maven依赖分析**

- 根据Maven坐标自动下载jar包及其依赖
- 支持私有Maven仓库和SNAPSHOT版本
- 批量查找指定的类

✅ **类反编译**

- 使用javap反编译Java字节码
- 获取完整的类结构信息
- 支持接口、抽象类、普通类

✅ **一站式服务**

- 查找+反编译一步到位
- 批量处理多个类
- JSON格式返回结果

## 架构

```
┌─────────────────┐         MCP Protocol          ┌──────────────────┐
│   MCP Client    │◄────────────────────────────► │   MCP Server     │
│                 │   (stdio/JSON-RPC)            │                  │
└─────────────────┘                               └──────────────────┘
                                                           │
                                                           ▼
                                                  ┌──────────────────┐
                                                  │ MavenJarAnalyzer │
                                                  └──────────────────┘
                                                           │
                                                           ▼
                                          ┌────────────────┴────────────────┐
                                          │                                 │
                                          ▼                                 ▼
                                    ┌─────────┐                      ┌──────────┐
                                    │  Maven  │                      │  javap   │
                                    └─────────┘                      └──────────┘

```

## 安装依赖

```bash
# 安装Python依赖
pip install mcp javatools

# 确保Maven和Java已安装
mvn --version
java -version

```

## 快速开始

### 1. 启动MCP服务器

```bash
python3 maven_jar_mcp_server.py

```

服务器通过stdio与客户端通信。

### 2. 使用测试客户端

```bash
python3 test_mcp_client.py

```

### 3. 在Cursor中使用

在Cursor配置文件中添加：

```json
{
  "mcpServers": {
    "maven-jar-analyzer": {
      "command": "python3",
      "args": ["/path/to/maven_jar_mcp_server.py"],
      "env": {}
    }
  }
}

```

## API文档

### 工具1: analyze_maven_dependency

分析Maven依赖并查找指定的类。

**请求参数：**

```json
{
  "dependencies": [
    {
      "groupId": "com.example",
      "artifactId": "my-library",
      "version": "1.0.0"
    }
  ],
  "target_classes": ["MyClass", "AnotherClass"],
  "repositories": [
    {
      "id": "my-repo",
      "name": "My Repository",
      "url": "<https://my-repo.com/maven>",
      "snapshots": "true"
    }
  ],
  "work_dir": "./maven_temp"
}

```

**响应示例：**

```json
{
  "found_classes": {
    "MyClass": [
      {
        "class_name": "com.example.MyClass",
        "jar_path": "/path/to/jar",
        "file_path": "com/example/MyClass.class"
      }
    ]
  },
  "jar_files": ["/path/to/jar1", "/path/to/jar2"],
  "work_dir": "./maven_temp",
  "summary": {
    "total_jars": 2,
    "found_classes_count": 1,
    "missing_classes": ["AnotherClass"]
  }
}

```

### 工具2: decompile_class

反编译指定的类。

**请求参数：**

```json
{
  "jar_path": "/path/to/library.jar",
  "class_file_path": "com/example/MyClass.class"
}

```

**响应示例：**

```json
{
  "class_name": "com.example.MyClass",
  "jar_path": "/path/to/library.jar",
  "class_file_path": "com/example/MyClass.class",
  "decompiled_code": "Compiled from \\"MyClass.java\\"\\npublic class com.example.MyClass {\\n  ...\\n}"
}

```

### 工具3: find_and_decompile_classes

一站式服务：查找并反编译所有类。

**请求参数：** 同 `analyze_maven_dependency`

**响应示例：**

```json
{
  "found_classes": { ... },
  "decompiled_classes": {
    "MyClass": "Compiled from \\"MyClass.java\\"...",
    "AnotherClass": "..."
  },
  "jar_files": [...],
  "work_dir": "./maven_temp",
  "summary": { ... }
}

```

## 使用示例

### Python客户端示例

```python
import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def analyze_dependency():
    server_params = StdioServerParameters(
        command="python3",
        args=["maven_jar_mcp_server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "find_and_decompile_classes",
                arguments={
                    "dependencies": [{
                        "groupId": "com.google.guava",
                        "artifactId": "guava",
                        "version": "31.1-jre"
                    }],
                    "target_classes": ["Lists", "Maps"]
                }
            )

            print(json.loads(result.content[0].text))

asyncio.run(analyze_dependency())

```

### Cursor AI对话示例

```
你: 帮我分析 com.example.MyClass:org-test-order-client:1.0.0-SNAPSHOT 这个依赖中的 TestOrderClient 类

AI: 我来帮你分析这个类...
[调用 find_and_decompile_classes 工具]

结果：
- TestOrderClient 是一个接口
- 包含方法：retrieveTestOrderList(CommonRequest<RetrieveTestOrderListForMssQuery>)
- 返回类型：PaginationResult<List<RetrieveTestOrderListForMssResp>>

```

## 配置说明

### Maven仓库配置

对于私有仓库或SNAPSHOT版本，需要配置仓库信息：

```json
{
  "repositories": [
    {
      "id": "company-snapshots",
      "name": "Company Snapshot Repository",
      "url": "<https://maven.company.com/snapshots>",
      "snapshots": "true"
    }
  ]
}

```

### Maven认证

如果需要认证，在 `~/.m2/settings.xml` 中配置：

```xml
<settings>
  <servers>
    <server>
      <id>company-snapshots</id>
      <username>your-username</username>
      <password>your-password</password>
    </server>
  </servers>
</settings>

```

## 项目结构

```
.
├── maven_jar_analyzer.py      # 核心分析器
├── maven_jar_mcp_server.py    # MCP服务器
├── README_MCP.md              # 本文档
└── maven_temp/                # 临时工作目录
    ├── pom.xml
    └── dependencies/
        └── *.jar

```

## 常见问题

### Q1: Maven下载失败怎么办？

A: 检查以下项：

1. Maven配置是否正确（`mvn --version`）
2. 网络连接是否正常
3. 仓库URL是否正确
4. 认证信息是否配置

### Q2: 找不到类怎么办？

A: 可能原因：

1. 类名拼写错误（支持简单类名，不需要包路径）
2. 版本不对，类不存在该版本中
3. jar包下载不完整

### Q3: 反编译失败怎么办？

A: 确保：

1. Java环境已正确安装（`java -version`）
2. javap命令可用
3. jar包文件完整且未损坏

## 性能优化

- 首次下载依赖会较慢，后续会使用Maven本地缓存
- 建议使用Maven镜像加速下载（配置settings.xml）
- 工作目录可复用，避免重复下载

## 贡献

欢迎提交Issue和Pull Request！