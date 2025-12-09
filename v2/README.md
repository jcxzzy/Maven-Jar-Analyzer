# Maven Jar Analyzer MCP 架构部署指南
**版本**: 2.0.0

**最后更新**: 2025-11-06

**协议**: MCP 2024-11-05 (streamable_http)

---

## 📐 系统架构

### 架构图

```
┌─────────────────────────────────────────────────────────────┐
│              Github Copilot IDE / MCP Client                │
│              (MCP streamable_http 协议)                      │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP + JSON-RPC
                         │ Port: 8001
┌────────────────────────▼────────────────────────────────────┐
│              MCP Proxy Server (代理层)                       │
│              maven_jar_mcp_proxy.py                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ - 接收 MCP JSON-RPC 请求 (initialize, tools/*)         │  │
│  │ - 转发请求到远程服务器                                   │  │
│  │ - 返回结构化 MCP 响应                                   │  │
│  │ - 支持健康检查和监控                                     │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP REST API
                         │ Port: 8000
┌────────────────────────▼────────────────────────────────────┐
│           Remote Maven Server (执行层)                       │
│           maven_jar_remote_server.py                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ - 执行 Maven 命令                                     │   │
│  │ - 下载 JAR 包及依赖                                    │   │
│  │ - 搜索和定位类文件                                      │   │
│  │ - 反编译 Java 类 (CFR)                                 │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │ Maven CLI
                         │
┌────────────────────────▼────────────────────────────────────┐
│              Maven Repository (存储层)                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ - Maven Central Repository                           │   │
│  │ - 私有 Maven 仓库 (可选)                               │   │
│  │ - 本地 Maven 缓存 (~/.m2/repository)                   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

```

---

## 🧩 核心组件清单

### 1. MCP Proxy Server (代理层)

**文件**: `maven_jar_mcp_proxy.py`

**职责**:

- 实现 MCP streamable_http 协议
- 处理 JSON-RPC 请求 (initialize, tools/list, tools/call)
- 转发工具调用到远程 Maven 服务器
- 提供健康检查和监控端点

**依赖**:

```python
# Python 包依赖
mcp >= 0.1.0           # MCP 协议库
fastapi >= 0.104.0     # Web 框架
uvicorn >= 0.24.0      # ASGI 服务器
httpx >= 0.25.0        # HTTP 客户端
sse-starlette >= 1.6.0 # SSE 支持

```

**配置项**:

- `REMOTE_SERVER_URL`: 远程 Maven 服务器地址 (默认: `http://localhost:8000`)
- `SERVER_HOST`: 监听地址 (默认: `0.0.0.0`)
- `SERVER_PORT`: 监听端口 (默认: `8001`)
- `HTTP_TIMEOUT`: HTTP 超时时间 (默认: `300.0` 秒)

**端点**:

- `GET /` - 服务器信息
- `POST /` - JSON-RPC 处理 (MCP 协议入口)
- `GET /health` - 健康检查
- `GET /mcp` - MCP 元数据 (兼容)
- `POST /mcp/tools/list` - 列出工具 (兼容)
- `POST /mcp/tools/call` - 调用工具 (兼容)
- `GET /mcp/sse` - SSE 流 (未来支持)

**启动命令**:

```bash
REMOTE_SERVER_URL=http://localhost:8000 python3 maven_jar_mcp_proxy.py

```

---

### 2. Remote Maven Server (执行层)

**文件**: `maven_jar_remote_server.py`

**职责**:

- 执行实际的 Maven 依赖解析和下载
- 在 JAR 包中搜索 Java 类
- 使用 CFR 反编译 Java 字节码
- 管理临时工作目录和缓存

**依赖**:

```python
# Python 包依赖
fastapi >= 0.104.0     # Web 框架
uvicorn >= 0.24.0      # ASGI 服务器

# 系统依赖
maven >= 3.6.0         # Maven 构建工具
java >= 1.8            # Java 运行时环境
cfr                    # Java 反编译器

```

**配置项**:

- `SERVER_HOST`: 监听地址 (默认: `0.0.0.0`)
- `SERVER_PORT`: 监听端口 (默认: `8000`)
- `MAVEN_HOME`: Maven 安装路径
- `JAVA_HOME`: Java 安装路径

**工具接口**:

1. **analyze_maven_dependency**
    - 输入: Maven 坐标、目标类名、仓库配置
    - 输出: 找到的类信息、JAR 路径列表、工作目录
2. **decompile_class**
    - 输入: JAR 路径、类文件路径
    - 输出: 反编译后的 Java 源代码
3. **find_and_decompile**
    - 输入: Maven 坐标、目标类名
    - 输出: 类信息 + 反编译代码 (一站式服务)

**端点**:

- `GET /health` - 健康检查
- `POST /analyze` - 分析依赖并查找类
- `POST /decompile` - 反编译指定类
- `POST /find_and_decompile` - 一站式查找并反编译

**启动命令**:

```bash
python3 maven_jar_remote_server.py

```

---

### 3. 外部工具依赖

### Maven (必需)

**版本要求**: >= 3.6.0

**安装方法**:

```bash
# macOS
brew install maven

# Ubuntu/Debian
sudo apt-get install maven

# CentOS/RHEL
sudo yum install maven

# 验证
mvn -version

```

**配置文件**: `~/.m2/settings.xml`

```xml
<settings>
  <mirrors>
    <mirror>
      <id>aliyun</id>
      <mirrorOf>central</mirrorOf>
      <url><https://maven.aliyun.com/repository/public></url>
    </mirror>
  </mirrors>
</settings>

```

### Java (必需)

**版本要求**: >= 1.8 (JDK 8+)

**安装方法**:

```bash
# macOS
brew install openjdk@11

# Ubuntu/Debian
sudo apt-get install openjdk-11-jdk

# CentOS/RHEL
sudo yum install java-11-openjdk-devel

# 验证
java -version

```

### CFR (必需)

**版本**: 最新版

**安装方法**:

```bash
# 下载 CFR
cd ~/.local/bin
wget <https://github.com/leibnitz27/cfr/releases/latest/download/cfr.jar>

# 或使用项目提供的版本
cp /path/to/project/cfr-0.152.jar ~/.local/bin/cfr.jar

# 创建启动脚本
echo '#!/bin/bash' > ~/.local/bin/cfr
echo 'java -jar ~/.local/bin/cfr.jar "$@"' >> ~/.local/bin/cfr
chmod +x ~/.local/bin/cfr

# 验证
cfr --version

```

### Python (必需)

**版本要求**: >= 3.8

**依赖包**:

```bash
# 安装所有依赖
pip install -r requirements.txt

# 或手动安装
pip install mcp fastapi uvicorn httpx sse-starlette

```

---

## 📦 依赖关系图

```
┌─────────────────────┐
│Github Copilot Client│
└──────────┬──────────┘
           │ 依赖
           ▼
┌─────────────────────┐
│  MCP Proxy Server   │
│  ┌───────────────┐  │
│  │ Python 3.8+   │  │
│  │ mcp           │  │
│  │ fastapi       │  │
│  │ uvicorn       │  │
│  │ httpx         │  │
│  │ sse-starlette │  │
│  └───────────────┘  │
└──────────┬──────────┘
           │ 依赖
           ▼
┌─────────────────────┐
│ Remote Maven Server │
│  ┌───────────────┐  │
│  │ Python 3.8+   │  │
│  │ fastapi       │  │
│  │ uvicorn       │  │
│  └───────┬───────┘  │
│          │ 调用      │
│  ┌───────▼───────┐  │
│  │ Maven 3.6+    │  │
│  │ Java 1.8+     │  │
│  │ CFR (latest)  │  │
│  └───────────────┘  │
└──────────┬──────────┘
           │ 访问
           ▼
┌─────────────────────┐
│  Maven Repository   │
│  - Maven Central    │
│  - 私有仓库 (可选)    │
│  - 本地缓存          │
└─────────────────────┘

```

---

## 🚀 部署步骤

### 前置条件检查

```bash
# 1. 检查 Python 版本
python3 --version  # 应该 >= 3.8

# 2. 检查 Java 版本
java -version      # 应该 >= 1.8

# 3. 检查 Maven 版本
mvn -version       # 应该 >= 3.6.0

# 4. 检查 CFR
cfr --version || echo "CFR 未安装"

# 5. 检查端口占用
lsof -i :8000      # Remote Maven Server
lsof -i :8001      # MCP Proxy Server

```

### 步骤 1: 安装 Python 依赖

```bash
# 安装所有依赖
pip3 install -r requirements.txt

# 或手动安装
pip3 install mcp fastapi uvicorn httpx sse-starlette pydantic

```

**验证安装**:

```bash
python3 -c "import mcp, fastapi, uvicorn, httpx; print('✅ 依赖安装成功')"

```

---

### 步骤 2: 安装外部工具

### 安装 Maven

```bash
# macOS
brew install maven

# Ubuntu/Debian
sudo apt-get update
sudo apt-get install maven

# CentOS/RHEL
sudo yum install maven

# 验证
mvn -version

```

### 安装 Java

```bash
# macOS
brew install openjdk@11
echo 'export PATH="/usr/local/opt/openjdk@11/bin:$PATH"' >> ~/.zshrc

# Ubuntu/Debian
sudo apt-get install openjdk-11-jdk

# CentOS/RHEL
sudo yum install java-11-openjdk-devel

# 验证
java -version
javac -version

```

### 安装 CFR

```bash
# 创建目录
mkdir -p ~/.local/bin

# 下载 CFR
cd ~/.local/bin
wget <https://github.com/leibnitz27/cfr/releases/latest/download/cfr.jar>

# 创建启动脚本
cat > ~/.local/bin/cfr << 'EOF'
#!/bin/bash
java -jar ~/.local/bin/cfr.jar "$@"
EOF

chmod +x ~/.local/bin/cfr

# 添加到 PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# 验证
cfr --version

```

---

### 步骤 3: 启动 Remote Maven Server

```bash
# 方式 1: 直接启动 (前台运行，便于调试)
python3 maven_jar_remote_server.py

# 方式 2: 后台运行
nohup python3 maven_jar_remote_server.py > remote_server.log 2>&1 &

# 方式 3: 指定配置
SERVER_HOST=0.0.0.0 SERVER_PORT=8000 python3 maven_jar_remote_server.py

# 方式 4: 使用启动脚本
./start_remote_server.sh

```

**验证服务**:

```bash
# 健康检查
curl <http://localhost:8000/health>

# 应返回
{
  "status": "healthy"
}

```

---

### 步骤 4: 启动 MCP Proxy Server

```bash
# 方式 1: 直接启动 (前台运行)
REMOTE_SERVER_URL=http://localhost:8000 python3 maven_jar_mcp_proxy.py

# 方式 2: 后台运行
nohup REMOTE_SERVER_URL=http://localhost:8000 python3 maven_jar_mcp_proxy.py > mcp_proxy.log 2>&1 &

# 方式 3: 远程 Maven 服务器
REMOTE_SERVER_URL=http://remote-ip:8000 python3 maven_jar_mcp_proxy.py

```

**验证服务**:

```bash
# 健康检查
curl <http://localhost:8001/health>

# 应返回
{
  "status": "healthy",
  "remote_server_healthy": true,
  "remote_server_url": "<http://localhost:8000>"
}

# 测试 Initialize
curl -X POST <http://localhost:8001/> \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

# 测试 Tools/List
curl -X POST <http://localhost:8001/> \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

```

---

### 步骤 5: 配置 Github Copilot

**添加配置**:

```json
{
  "mcpServers": {
    "maven-jar-analyzer": {
      "type": "streamable_http",
      "url": "<http://远程MCP服务IP:8001>",
      "autoApprove": [],
      "disabled": false
    }
  }
}

```

---

### 步骤 6: 验证集成

### 在 Github Copilot 中测试

1. 打开任意文件
2. 输入: `@maven-jar-analyzer`
3. 应该看到工具提示和 3 个可用工具：
    - `analyze_maven_dependency`
    - `decompile_class`
    - `find_and_decompile`

### 测试工具调用

在 Github Copilot 中输入：

```
@maven-jar-analyzer 分析依赖：
groupId: org.apache.commons
artifactId: commons-lang3
version: 3.12.0
查找类: StringUtils

```

应该返回类的位置信息。

---

## 📊 部署架构选择

### 单机部署 (开发/测试)

```
┌─────────────────────────────────────┐
│         Local Machine               │
│  ┌──────────────────────────────┐   │
│  │  Github Copilot IDE               │   │
│  └───────────┬──────────────────┘   │
│              │                      │
│  ┌───────────▼──────────────────┐   │
│  │  MCP Proxy (Port 8001)       │   │
│  └───────────┬──────────────────┘   │
│              │                      │
│  ┌───────────▼──────────────────┐   │
│  │  Remote Maven Server         │   │
│  │  (Port 8000)                 │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘

```

**优点**: 简单易部署，便于调试
**缺点**: 需要本地安装 Maven 和 Java

**部署命令**:

```bash
# 终端 1: 启动 Remote Maven Server
python3 maven_jar_remote_server.py

# 终端 2: 启动 MCP Proxy
REMOTE_SERVER_URL=http://localhost:8000 python3 maven_jar_mcp_proxy.py

```

---

### 分离部署 (生产推荐)

```
┌─────────────────┐         ┌──────────────────────┐
│  Client Machine │         │   Maven Server       │
│  ┌───────────┐  │         │  ┌───────────────┐   │
│  │  Copilot  │  │         │  │  Remote Maven │   │
│  └─────┬─────┘  │         │  │  Server       │   │
│        │        │         │  │  (Port 8000)  │   │
│  ┌─────▼─────┐  │  HTTP   │  └───────────────┘   │
│  │ MCP Proxy │  ├────────►│  ┌───────────────┐   │
│  │(Port 8001)│  │         │  │  Maven + Java │   │
│  └───────────┘  │         │  │  + CFR        │   │
└─────────────────┘         │  └───────────────┘   │
                            └──────────────────────┘

```

**优点**:

- 客户端无需 Maven 环境
- 集中管理依赖和缓存
- 多用户共享
- 资源隔离

**部署步骤**:

**服务器端**:

```bash
# 安装依赖
pip3 install fastapi uvicorn pydantic
sudo apt-get install maven openjdk-11-jdk

# 启动服务
python3 maven_jar_remote_server.py

# 后台运行
nohup python3 maven_jar_remote_server.py > remote.log 2>&1 &

```

**客户端**:

```bash
# 安装依赖
pip3 install mcp fastapi uvicorn httpx sse-starlette

# 启动代理 (指向远程服务器)
REMOTE_SERVER_URL=http://server-ip:8000 python3 maven_jar_mcp_proxy.py

# 后台运行
nohup REMOTE_SERVER_URL=http://server-ip:8000 python3 maven_jar_mcp_proxy.py > proxy.log 2>&1 &

```

---

## 🔧 高级配置

### Maven 镜像配置

创建 `~/.m2/settings.xml`:

```xml
<settings xmlns="<http://maven.apache.org/SETTINGS/1.0.0>"
    xmlns:xsi="<http://www.w3.org/2001/XMLSchema-instance>"
    xsi:schemaLocation="<http://maven.apache.org/SETTINGS/1.0.0>
    <http://maven.apache.org/xsd/settings-1.0.0.xsd>">

  <mirrors>
    <!-- 阿里云镜像 (推荐国内用户) -->
    <mirror>
      <id>aliyun</id>
      <name>Aliyun Maven</name>
      <url><https://maven.aliyun.com/repository/public></url>
      <mirrorOf>central</mirrorOf>
    </mirror>

    <!-- 华为云镜像 -->
    <mirror>
      <id>huawei</id>
      <name>Huawei Maven</name>
      <url><https://repo.huaweicloud.com/repository/maven/></url>
      <mirrorOf>central</mirrorOf>
    </mirror>
  </mirrors>

  <!-- 私有仓库配置 (如果需要) -->
  <servers>
    <server>
      <id>private-repo</id>
      <username>your-username</username>
      <password>your-password</password>
    </server>
  </servers>
</settings>

```

### 环境变量完整列表

### Remote Maven Server

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `SERVER_HOST` | 监听地址 | `0.0.0.0` |
| `SERVER_PORT` | 监听端口 | `8000` |
| `MAVEN_HOME` | Maven 路径 | 自动检测 |
| `JAVA_HOME` | Java 路径 | 自动检测 |
| `CFR_PATH` | CFR JAR 路径 | `~/.local/bin/cfr.jar` |

### MCP Proxy Server

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `REMOTE_SERVER_URL` | 远程服务器地址 | `http://localhost:8000` |
| `SERVER_HOST` | 监听地址 | `0.0.0.0` |
| `SERVER_PORT` | 监听端口 | `8001` |
| `HTTP_TIMEOUT` | HTTP 超时(秒) | `300.0` |

### 日志配置

**启用详细日志**:

```bash
# Remote Maven Server
LOGLEVEL=DEBUG python3 maven_jar_remote_server.py

# MCP Proxy
LOGLEVEL=DEBUG python3 maven_jar_mcp_proxy.py

```

**日志文件**:

```bash
# 输出到文件
python3 maven_jar_remote_server.py > logs/remote.log 2>&1
python3 maven_jar_mcp_proxy.py > logs/proxy.log 2>&1

# 使用 tee 同时输出到控制台和文件
python3 maven_jar_remote_server.py 2>&1 | tee logs/remote.log

```

---

### 第2步：在本地配置MCP Proxy

### 方案A：HTTP/SSE模式（推荐）

### 安装依赖

```bash
# Linux/macOS
pip3 install mcp httpx fastapi sse-starlette uvicorn

# Windows
pip install mcp httpx fastapi sse-starlette uvicorn

# 如果使用虚拟环境（推荐）
python3 -m venv mcp_venv
source mcp_venv/bin/activate  # Linux/macOS
# 或
.\\\\mcp_venv\\\\Scripts\\\\activate.bat  # Windows CMD
pip install mcp httpx fastapi sse-starlette uvicorn

```

### 配置和启动

```bash
# 1. 配置远程服务器地址
export REMOTE_SERVER_URL=http://your-server-ip:8000
export PROXY_HOST=0.0.0.0
export PROXY_PORT=8001

# 2. 启动HTTP/SSE代理服务器
python3 maven_jar_mcp_proxy.py

# 服务将监听 <http://0.0.0.0:8001>

```

### 测试HTTP/SSE服务

```bash
# 1. 测试健康检查
curl <http://localhost:8001/health>

# 2. 列出工具
curl -X POST <http://localhost:8001/mcp/v1/tools/list>

# 3. 调用工具
curl -X POST <http://localhost:8001/mcp/v1/tools/call> \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "analyze_maven_dependency",
    "arguments": {
      "dependencies": [{
        "groupId": "org.springframework",
        "artifactId": "spring-core",
        "version": "5.3.20"
      }],
      "target_classes": ["ApplicationContext"]
    }
  }'

# 4. 测试SSE连接
curl -N <http://localhost:8001/sse>

```

### 方案B：stdio模式（旧版兼容）

### 安装依赖

```bash
# Linux/macOS
pip3 install mcp httpx

# Windows
pip install mcp httpx

# 如果使用虚拟环境（推荐）
python3 -m venv mcp_venv
source mcp_venv/bin/activate
pip install mcp httpx

```

### 配置

```bash
# 配置远程服务器地址
# 方式A：创建.env文件
cat > .env << EOF
REMOTE_SERVER_URL=http://your-server-ip:8000
EOF

# 方式B：设置环境变量（临时）
export REMOTE_SERVER_URL=http://your-server-ip:8000

# 方式C：设置环境变量（永久）
echo 'export REMOTE_SERVER_URL=http://your-server-ip:8000' >> ~/.bashrc
source ~/.bashrc

```

### 注意

stdio模式仅用于Github Copilot集成，不能独立测试。需要通过Github Copilot配置文件使用。

### Windows系统安装步骤

```powershell
# 1. 确保Python环境已安装（需要Python 3.10+）
# 打开PowerShell或CMD
python --version

# 2. 安装本地依赖
pip install mcp httpx

# 如果使用虚拟环境（推荐）
python -m venv mcp_venv
.\\mcp_venv\\Scripts\\Activate.ps1  # PowerShell
# 或
.\\mcp_venv\\Scripts\\activate.bat  # CMD

pip install mcp httpx

# 3. 配置远程服务器地址
# 方式A：创建.env文件（使用记事本或其他编辑器）
# 创建文件 .env，内容为：
# REMOTE_SERVER_URL=http://your-server-ip:8000

# 方式B：设置环境变量（临时 - PowerShell）
$env:REMOTE_SERVER_URL="<http://your-server-ip:8000>"

# 方式C：设置环境变量（临时 - CMD）
set REMOTE_SERVER_URL=http://your-server-ip:8000

# 方式D：设置环境变量（永久）
# 右键"此电脑" -> 属性 -> 高级系统设置 -> 环境变量
# 或使用命令（PowerShell管理员）：
[System.Environment]::SetEnvironmentVariable("REMOTE_SERVER_URL", "<http://your-server-ip:8000>", "User")

# 4. 测试连接
python maven_jar_mcp_proxy.py

```

### 验证安装

```bash
# Linux/macOS
onse.getData();python3 -c "import mcp; import httpx; print('✓ Dependencies installed successfully')"

# Windows
python -c "import mcp; import httpx; print('✓ Dependencies installed successfully')"

```

### 第3步：配置Github Copilot

在Github Copilot的MCP配置文件中添加：

**macOS**: `~/Library/Application Support/Github Copilot/mcp_settings.json`**Linux**: `~/.config/Github Copilot/mcp_settings.json`**Windows**: `%APPDATA%\\Github Copilot\\mcp_settings.json`

```json
{
  "mcpServers": {
    "maven-jar-analyzer": {
      "command": "python3",
      "args": ["/absolute/path/to/maven_jar_mcp_proxy.py"],
      "env": {
        "REMOTE_SERVER_URL": "<http://your-server-ip:8000>"
      }
    }
  }
}

```

### 第4步：重启Github Copilot

完全退出并重新启动Github Copilot以加载MCP配置。

## 🧪 测试

### 测试远程服务端

```bash
curl <http://your-server-ip:8000/health>
# 应返回: {"status":"healthy"}

```

### 测试完整流程

在Github Copilot中询问智能体：
```
请使用Maven jar analyzer工具分析以下依赖：
- groupId: org.springframework.security.oauth
- artifactId: spring-security-oauth2
- version: 2.3.4.RELEASE
查找类：AuthorizationServerConfigurerAdapter

```

## 📝 配置说明

### 远程服务端环境变量

- `SERVER_HOST`: 监听地址，默认 `0.0.0.0`
- `SERVER_PORT`: 监听端口，默认 `8000`

### MCP Proxy环境变量

- `REMOTE_SERVER_URL`: 远程服务端地址，默认 `http://localhost:8000`

## 🔧 故障排查

### 问题1：Github Copilot连接MCP失败

**检查**：

```bash
# 确保proxy可以独立运行
python3 maven_jar_mcp_proxy.py
# 应该看到：Starting Maven Jar Analyzer MCP Proxy Server...

```

### 问题2：远程服务器连接失败

**检查**：

```bash
# 1. 检查远程服务器是否运行
curl <http://your-server-ip:8000/health>

# 2. 检查防火墙
# 确保端口8000已开放

# 3. 查看proxy日志
# 在stderr中会显示连接状态

```

### 问题3：Maven下载失败

**检查**：

- 远程服务器是否有Maven
- Maven仓库配置是否正确
- 网络连接是否正常

## 🔐 安全建议

1. **生产环境**：
    - 使用HTTPS（添加nginx反向代理）
    - 添加认证机制（API密钥）
    - 限制访问IP
2. **网络**：
    - 使用VPN或内网部署
    - 配置防火墙规则

## 📂 文件说明

- `maven_jar_remote_server.py`: 远程HTTP服务端
- `maven_jar_mcp_proxy.py`: MCP协议代理服务器
- `maven_jar_analyzer.py`: Maven分析核心逻辑
- `requirements.txt`: Python依赖包列表
- `.env.example`: 环境变量配置示例

## ✅ 验证清单

- [ ]  远程服务器已安装Maven
- [ ]  远程服务端可以访问 `/health`
- [ ]  MCP Proxy可以连接远程服务端
- [ ]  Github Copilot配置文件正确
- [ ]  Github Copilot已重启
- [ ]  智能体可以看到maven工具

## 📖 API文档

远程服务端启动后，访问以下地址查看API文档：

- Swagger UI: `http://your-server-ip:8000/docs`
- ReDoc: `http://your-server-ip:8000/redoc`

## 🎯 使用示例

```python
# 通过智能体使用
"请分析org.springframework.security.oauth:spring-security-oauth2:2.3.4.RELEASE，找到查找类：AuthorizationServerConfigurerAdapter类并反编译"

```

## 💡 优势

相比旧架构的优势：

1. ✅ Maven环境集中管理
2. ✅ Github Copilot本地无需Maven
3. ✅ 支持远程执行和缓存
4. ✅ 便于维护和升级
5. ✅ 支持多用户共享