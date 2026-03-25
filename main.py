from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
import dashscope
from dashscope import Generation
from pydantic import BaseModel
from typing import List, Optional
import os
import json
import sqlite3
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


load_dotenv()
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY") ##"DASHSCOPE_API_KEY" +"你的API key"


app = FastAPI()

@app.get("/")
def serve_frontend():
    return FileResponse("index.html")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 优先从环境变量读取路径，如果没有则使用本地默认值
DB_PATH = os.getenv("DB_PATH", "chat.db")


# ═══════════════════════════════════════════════════════
# ─── 新增：数据库结构升级为双表设计 ───
#
# 旧版：只有 messages 表，所有消息混在一起
# 新版：
#   sessions 表 → 存每个会话的元信息（id、标题、创建时间）
#   messages 表 → 每条消息多一个 session_id 外键，
#                 表明这条消息属于哪个会话
#
# 关系：一个 session 对应多条 messages（一对多）
# ═══════════════════════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_PATH)

    # 会话表：存会话标题和创建时间
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 消息表：新增 session_id 字段，关联到 sessions 表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            ts         TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
    """)

    # ON DELETE CASCADE：删除会话时，该会话下的所有消息自动一并删除
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()

init_db()


# ── 数据库工具函数 ──

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")  # 每次连接都要开启外键支持
    return conn

def save_message(session_id: int, role: str, content: str):
    conn = db_connect()
    conn.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content)
    )
    conn.commit()
    conn.close()

def load_messages(session_id: int):
    conn = db_connect()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE session_id=? ORDER BY id ASC",
        (session_id,)
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]


# ── 请求体结构 ──

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    session_id: int          # ─── 新增：每次发消息必须指定所属会话 ───
    messages: List[Message]

class SaveRequest(BaseModel):
    session_id: int
    role: str
    content: str

class CreateSessionRequest(BaseModel):
    title: str               # 用户手动输入的会话名称


# ═══════════════════════════════════════════════════════
# ─── 新增：会话管理接口 ───
# ═══════════════════════════════════════════════════════

# 获取所有会话列表（按创建时间倒序，最新的在最上面）
@app.get("/sessions")
def get_sessions():
    conn = db_connect()
    rows = conn.execute(
        "SELECT id, title, created_at FROM sessions ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return {"sessions": [{"id": r[0], "title": r[1], "created_at": r[2]} for r in rows]}


# 新建会话（用户输入标题后调用）
@app.post("/sessions")
def create_session(req: CreateSessionRequest):
    conn = db_connect()
    cursor = conn.execute(
        "INSERT INTO sessions (title) VALUES (?)", (req.title,)
    )
    session_id = cursor.lastrowid  # 拿到自动生成的会话 id
    conn.commit()
    conn.close()
    return {"id": session_id, "title": req.title}


# ─── 新增：删除指定会话 ───
# 因为设置了 ON DELETE CASCADE，删会话时该会话下的消息自动删除
@app.delete("/sessions/{session_id}")
def delete_session(session_id: int):
    conn = db_connect()
    result = conn.execute(
        "DELETE FROM sessions WHERE id=?", (session_id,)
    )
    conn.commit()
    conn.close()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "deleted"}


# 获取某个会话的所有消息
@app.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: int):
    return {"messages": load_messages(session_id)}


# ── SSE 流式生成器（新增 session_id 参数）──
def stream_generator(session_id: int, messages: List[Message], user_message: str):

    # 保存用户消息到对应会话
    save_message(session_id, "user", user_message)

    recent = messages[-10:]
    context_prompt = ""
    for msg in recent:
        prefix = "用户" if msg.role == "user" else "AI"
        context_prompt += f"{prefix}: {msg.content}\n"

    responses = Generation.call(
        model="qwen-turbo",
        prompt=context_prompt,
        stream=True,
        incremental_output=True
    )

    for chunk in responses:
        try:
            text_piece = chunk.output.text
        except AttributeError:
            text_piece = chunk.output.get("text", "")

        if text_piece:
            payload = json.dumps({"text": text_piece}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    yield "data: [DONE]\n\n"


@app.post("/chat")
def chat(request: ChatRequest):
    user_message = request.messages[-1].content
    return StreamingResponse(
        stream_generator(request.session_id, request.messages, user_message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# 保存 AI 回答（前端收到 [DONE] 后调用）
@app.post("/save")
def save(req: SaveRequest):
    save_message(req.session_id, req.role, req.content)
    return {"status": "ok"}


# ── 启动命令 ──
# 1. 激活虚拟环境：
#    Windows:    venv\Scripts\activate
#    Mac/Linux:  source venv/bin/activate
#
# 2. 启动服务：
#    uvicorn main:app --reload
#网址 https://web-production-01606.up.railway.app