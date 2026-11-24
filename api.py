import uuid
import json
import openai
import os
import secrets
from datetime import date
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from db import init_db, list_budgets, query_records, add_record, update_record, delete_record, get_record, load_session, save_session
from agent import chat, SYSTEM_PROMPT, resume_chat
from fastapi.responses import FileResponse, JSONResponse



import logging
logger = logging.getLogger("agent")

app = FastAPI(title="记账 Agent API")   # 样板：创建那张"网址 → 函数"的表 fastapi做的就是查表调函数转JSON


APP_PASSWORD = os.getenv("APP_PASSWORD")             # 没设置就不检查（你本机自己用的情况）
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "100"))   # 每天最多发多少句
chat_count = {"date": None, "count": 0}              # 记录今天已经发了几句（存在内存里，重启清零）


@app.middleware("http")
async def check_password(request: Request, call_next):
    """设置了 APP_PASSWORD 时，除首页和 /health 外，每个请求都要带正确的口令"""
    if APP_PASSWORD and request.url.path not in ("/", "/health"):
        key = request.headers.get("X-Access-Key", "")
        if not secrets.compare_digest(key.encode(), APP_PASSWORD.encode()):
            return JSONResponse(status_code=401, content={"detail": "访问口令错误"})
    return await call_next(request)


def check_daily_limit():
    """今天的次数用完了就返回 429"""
    today = date.today().isoformat()
    if chat_count["date"] != today:      # 换了一天，从 0 开始重新计数
        chat_count["date"] = today
        chat_count["count"] = 0
    if chat_count["count"] >= DAILY_LIMIT:
        raise HTTPException(status_code=429, detail="今天的使用次数已用完，明天再试")
    chat_count["count"] += 1


#2：建表。提示见下面
init_db()

#请求到达
#  ↓ 第1关：FastAPI 查网址表 → 没这个网址              → 404（自动）
#  ↓ 第2关：Pydantic 检查格式 → 缺字段、类型不对        → 422（自动，你的函数根本没运行）
#  ↓ 第3关：进入你的函数，你自己判断
#  │     记录或会话不存在      → 你 raise 404
#  │     内容不合规则（金额≤0） → 你 raise 400
#  │     状态不允许（有待确认的删除）→ 你 raise 409
#  ↓ 你的代码自己出 bug 崩了                         → 500（看终端里的 Traceback）
#  ↓ 一切正常 → 200，新建成功是 201

@app.get("/")
def index():
    return FileResponse("index.html")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/budgets")
def get_budgets():
    return list_budgets()

@app.get("/records")
def get_records(record_type: str | None = None, category: str | None = None, start_date: str | None = None, end_date: str | None = None):
#参数是字符串或None或不传默认None
    return query_records(record_type=record_type, category=category, start_date=start_date, end_date=end_date)
    # 用关键字传参 record_type=record_type 更稳，
    # 这样就算以后 query_records 的参数顺序变了也不会传错

#继承了 BaseModel 之后，构造函数和类型检查 Pydantic 都替你做好了
class RecordIn(BaseModel):
    record_type: str
    amount: float
    category: str
    remark: str = ""



@app.post("/records", status_code=201)    # 样板：新建成功返回 201，而不是默认的 200
def create_record(record: RecordIn):

    result = add_record(**record.model_dump())

    if "error" in result:
        raise HTTPException(status_code = 400, detail=result["error"])

    return result


#   提示：update_record 是用 is not None 判断有没有传的，所以 None 正好表示"不改"
class RecordUpdate(BaseModel):
    record_type: str | None = None
    amount: float | None = None
    category: str | None = None
    remark: str | None = None


@app.patch("/records/{record_id}")
def modify_record(record_id: int, data: RecordUpdate):

    if get_record(record_id) is None:
        raise HTTPException(status_code=404, detail="找不到该记录")

    result = update_record(record_id, **data.model_dump())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@app.delete("/records/{record_id}")
def remove_record(record_id: int):

    result = delete_record(record_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result



class ChatIn(BaseModel):
    message: str
    session_id: str | None = None      # 第一次不带，服务器会发一个

def build_response(rid, messages, respond):
    """把 chat 的结果打包成返回给浏览器的字典，并把会话写回数据库"""
    if respond["type"] == "reply":                       # 不需要确认：直接回复
        save_session(rid, messages, None)
        return {"session_id": rid, "type": "reply", "reply": respond["content"]}

    # 需要确认：先把便签存进库
    pending = respond["pending"]
    save_session(rid, messages, pending)

    # 1. 把参数字符串解析成字典；模型给的参数不是合法 JSON 时当成空字典，接口不能因此报 500
    try:
        args = json.loads(pending["arguments"] or "{}")
    except json.JSONDecodeError:
        args = {}

    # 2. 参数里有 record_id 才去查记录；别的需要确认的工具可能没有这个参数
    record_id = args.get("record_id")
    record = get_record(record_id) if record_id is not None else None

    # 3. 告诉前端要确认执行的是哪个工具、参数是什么，没有记录时也能显示
    return {
        "session_id": rid,
        "type": "confirm",
        "record": record,
        "tool": pending["name"],
        "arguments": args,
    }




@app.post("/chat")
def chat_api(body: ChatIn):
    check_daily_limit() 
    rid = body.session_id

    if rid is None:
        #新会话
        rid=str(uuid.uuid4())
        messages=[{"role": "system", "content": SYSTEM_PROMPT}]#相当于初始化messages
        pending=None
    else:
        # 旧会话
        session=load_session(rid)#有rid就是旧会话，要读取

        if session is None:
            raise HTTPException(status_code=404, detail="没有该会话")
        
        messages=session["messages"]
        pending=session["pending"]

    if pending is not None:
        raise HTTPException(status_code=409, detail="有待确认的删除，请先确认或取消")

    messages.append({"role": "user", "content": body.message})
    try:
        respond=chat(messages)
    except openai.APIError as e:
        logger.warning(f"[模型错误]{e}")
        raise HTTPException(status_code=503, detail="模型服务暂时不可用，请稍后重试")

    return build_response(rid, messages, respond)



class ConfirmIn(BaseModel):
    session_id: str
    approved: bool


@app.post("/chat/confirm")
def chat_confirm(body: ConfirmIn):
    rid = body.session_id

    session=load_session(rid)

    if session is None:
        raise HTTPException(status_code=404, detail="该会话不存在")

    messages=session["messages"]
    pending=session["pending"]

    if pending is None:
        raise HTTPException(status_code=409, detail="没有待确认的删除")

    try:
        respond=resume_chat(messages, pending, body.approved)
    except openai.APIError as e:
        logger.warning(f"[模型错误]{e}")
        raise HTTPException(status_code=503, detail="模型服务暂时不可用，请稍后重试")
    return build_response(rid, messages, respond)

