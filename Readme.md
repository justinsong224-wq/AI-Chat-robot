# 🤖 AI Chat Assistant

基于 FastAPI + AI 大模型构建的聊天助手，支持流式输出、Markdown 渲染、多会话管理、聊天记录持久化。

> 本项目以**通义千问（Qwen）**为默认示例，但后端设计支持替换为任意兼容 OpenAI 接口标准的模型。

---

## ✨ 功能特性

- **多会话管理**：左侧侧边栏新建/切换/删除会话，像 ChatGPT 一样
- **流式输出**：AI 回答逐字实时显示，无需等待完整响应
- **Markdown 渲染**：支持代码块、粗体、列表等格式化显示
- **聊天记录持久化**：SQLite 存储，重启服务器记录不丢失
- **上下文记忆**：每个会话保留最近 10 条对话作为上下文
- **Enter 发送 / Shift+Enter 换行**：符合用户习惯的输入方式

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | 原生 HTML / CSS / JavaScript |
| 后端 | FastAPI + Uvicorn |
| AI 模型 | 可替换（默认：阿里云通义千问 qwen-turbo） |
| 数据库 | SQLite（Python 内置） |
| 流式传输 | SSE（Server-Sent Events） |

---

## 📁 项目结构

```
AI-Chat-robot/
├── main.py           # FastAPI 后端（API 接口 + SSE 流式 + SQLite）
├── index.html        # 前端页面（聊天界面）
├── requirements.txt  # Python 依赖列表
├── .gitignore        # Git 忽略规则
├── .env              # 环境变量（API Key，不上传 GitHub）
├── chat.db           # SQLite 数据库（自动创建，不上传 GitHub）
└── venv/             # Python 虚拟环境（不上传 GitHub）
```

---

## 🚀 本地运行

### 1. 克隆项目

```bash
git clone https://github.com/你的用户名/AI-Chat-robot.git
cd AI-Chat-robot
```

### 2. 创建并激活虚拟环境

```bash
# 创建虚拟环境
python -m venv venv

# 激活（Windows）
venv\Scripts\activate

# 激活（Mac/Linux）
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置 API Key

在项目根目录新建 `.env` 文件：

```
DASHSCOPE_API_KEY=你的通义千问APIKey
```

> API Key 获取地址：[https://dashscope.console.aliyun.com](https://dashscope.console.aliyun.com)

### 5. 启动后端服务

```bash
uvicorn main:app --reload
```

后端运行在：`http://127.0.0.1:8000`

### 6. 打开前端页面

用 PyCharm 右上角浏览器图标打开 `index.html`，或起一个静态服务器：

```bash
python -m http.server 8080
# 访问 http://localhost:8080/index.html
```

---

## 🔄 替换为其他 AI 模型

本项目后端的模型调用集中在 `main.py` 的 `stream_generator()` 函数中，**只需修改这一处**即可替换为其他模型。以下是几种常见替换方案：

---

### 方案一：OpenAI / GPT 系列

```bash
pip install openai
```

```python
# .env 文件
OPENAI_API_KEY=你的OpenAI APIKey
```

```python
# main.py - 替换 stream_generator() 内的调用部分
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def stream_generator(session_id, messages, user_message):
    save_message(session_id, "user", user_message)

    recent = messages[-10:]
    openai_messages = [{"role": m.role, "content": m.content} for m in recent]

    stream = client.chat.completions.create(
        model="gpt-4o",   # 可换为 gpt-3.5-turbo 等
        messages=openai_messages,
        stream=True
    )

    for chunk in stream:
        piece = chunk.choices[0].delta.content or ""
        if piece:
            payload = json.dumps({"text": piece}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    yield "data: [DONE]\n\n"
```

---

### 方案二：Google Gemini

```bash
pip install google-generativeai
```

```python
# .env 文件
GEMINI_API_KEY=你的Gemini APIKey
```

```python
# main.py - 替换 stream_generator() 内的调用部分
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

def stream_generator(session_id, messages, user_message):
    save_message(session_id, "user", user_message)

    recent = messages[-10:]
    prompt = "\n".join(
        f"{'用户' if m.role == 'user' else 'AI'}: {m.content}"
        for m in recent
    )

    stream = model.generate_content(prompt, stream=True)

    for chunk in stream:
        piece = chunk.text or ""
        if piece:
            payload = json.dumps({"text": piece}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    yield "data: [DONE]\n\n"
```

---

### 方案三：Ollama（本地模型，完全免费）

适合不想使用云端 API、希望本地运行模型的场景。

```bash
# 先安装 Ollama：https://ollama.com
# 然后拉取模型（以 llama3 为例）
ollama pull llama3
```

```bash
pip install ollama
```

```python
# main.py - 替换 stream_generator() 内的调用部分
import ollama

def stream_generator(session_id, messages, user_message):
    save_message(session_id, "user", user_message)

    recent = messages[-10:]
    ollama_messages = [{"role": m.role, "content": m.content} for m in recent]

    stream = ollama.chat(
        model="llama3",   # 可换为 qwen2、mistral 等已拉取的模型
        messages=ollama_messages,
        stream=True
    )

    for chunk in stream:
        piece = chunk["message"]["content"] or ""
        if piece:
            payload = json.dumps({"text": piece}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    yield "data: [DONE]\n\n"
```

> 使用 Ollama 时无需配置任何 API Key，模型完全在本地运行。

---

## 📡 API 接口说明

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/sessions` | 获取所有会话列表 |
| `POST` | `/sessions` | 新建会话 |
| `DELETE` | `/sessions/{id}` | 删除指定会话及其消息 |
| `GET` | `/sessions/{id}/messages` | 获取指定会话的历史消息 |
| `POST` | `/chat` | 发送消息，返回 SSE 流式响应 |
| `POST` | `/save` | 保存 AI 回答到数据库 |

---

## ⚠️ 注意事项

- `.env` 文件和 `chat.db` 已加入 `.gitignore`，不会上传到 GitHub
- 请勿将 API Key 硬编码在代码里提交到公开仓库
- 首次运行会自动创建 `chat.db`，无需手动创建
- 如果从旧版本升级，需要删除旧的 `chat.db`，新版数据库结构已更新