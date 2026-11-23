import os
import json
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from db import (init_db, add_record, query_records, update_record,
                delete_record, get_record, set_budget, list_budgets)
import logging
import time

logging.basicConfig(
    level=logging.INFO,                                      # INFO 及以上的级别都记录
    format="%(asctime)s %(levelname)s %(message)s",           # 每行格式：时间 级别 内容
    handlers=[
        logging.FileHandler("agent.log", encoding="utf-8"),  # 写进文件，encoding 保证中文不乱码
        logging.StreamHandler(),                             # 同时输出到终端
    ],
)
logger = logging.getLogger("agent")


load_dotenv()

MODEL_TIMEOUT_SECONDS = 60#规定请求超时时间
MODEL_MAX_RETRIES = 2#规定最多重试次数

client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
    timeout=MODEL_TIMEOUT_SECONDS,
    max_retries=MODEL_MAX_RETRIES,
)
MODEL = os.getenv("MODEL")

# ===== 第1段：给模型的规则 =====
TODAY = datetime.now().strftime("%Y-%m-%d")

SYSTEM_PROMPT = f"""你是一个记账助手，帮用户记录和查询日常收支。
今天是{TODAY}。
规则：
1. 用户提到花了钱或收到钱时，调用 add_record 工具记账。
2. 金额不明确时，先向用户追问，不要自己编造金额。
3. 分类尽量从这些里选：餐饮、交通、购物、娱乐、生活费、工资、其他。
4. 记账成功后，用一句话告诉用户记了什么。
5. 工具返回 error 时，根据错误信息修正参数，或者向用户确认。
6. 用户问花了多少、记了几笔、某段时间的收支时，调用 query_records 查询，不要凭对话记忆回答。
7. 查询时，"今天""这个月""上周"这类说法要根据今天的日期换算成具体的 start_date 和 end_date。
8. 查询分类时，用和记账时一样的分类名，比如用户说"吃饭"就查"餐饮"。
9. 用户要修改或删除记录时，先调用 query_records 找到对应记录的 id，不要猜 id。
10. 符合条件的记录不止一条时，把这几条列出来让用户选，不要自己挑一条。
11. 删除时，用 query_records 找到唯一对应的记录后，直接调用 delete_record，不用在对话里先问用户。程序会在执行前自动向用户确认。如果工具返回用户取消，就告诉用户这笔记录已保留。
12. 修改不需要确认，改完告诉用户改前和改后的内容。
13. 用户设置或修改某个分类的每月预算时，调用 set_budget，分类名和记账时用的一样。用户没说是哪个分类时，先问清楚，不要根据上文猜。
14. 用户问预算还剩多少、有没有超支时，调用 list_budgets。
15. add_record 的结果里有 budget 时，记账回复里要顺便说本月这个分类已花多少、还剩多少；over_budget 为 true 时，提醒用户已经超支多少。
16.工具返回记录不存在时，要如实告诉用户，这条记录已经不存在（可能已在别处删除），不能说成是自己删除的。
17.看到工具结果已省略时，如果需要其中的数据，就重新调用工具查询，不要凭记忆回答。
18. 回答简洁，用中文。"""

# ===== 第2段：工具说明书 =====
tools = [
    {
        "type": "function",
        "function": {
            "name": "add_record",
            "description": "记录一笔收入或支出",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_type": {"type": "string", "enum": ["收入", "支出"], "description": "收入还是支出"},
                    "amount": {"type": "number", "description": "金额，单位元，必须大于0"},
                    "category": {"type": "string", "description": "分类，比如餐饮、交通、生活费"},
                    "remark": {"type": "string", "description": "备注，可以不填"},
                },
                "required": ["record_type", "amount", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_records",
            "description": "按条件查询记账记录，返回笔数、收入合计、支出合计和最近的记录。所有参数都可以不填，不填就是不限制",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_type": {"type": "string", "enum": ["收入", "支出"], "description": "只查收入或只查支出"},
                    "category": {"type": "string", "description": "分类，比如餐饮、交通"},
                    "start_date": {"type": "string", "description": "开始日期，格式 YYYY-MM-DD，包含这一天"},
                    "end_date": {"type": "string", "description": "结束日期，格式 YYYY-MM-DD，包含这一天"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_record",
            "description": "修改一条已有的记录。只填要修改的字段，没填的字段保持不变。record_id 要先用 query_records 查出来",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_id": {"type": "integer", "description": "要修改的记录 id"},
                    "record_type": {"type": "string", "enum": ["收入", "支出"], "description": "新的类型"},
                    "amount": {"type": "number", "description": "新的金额，必须大于0"},
                    "category": {"type": "string", "description": "新的分类"},
                    "remark": {"type": "string", "description": "新的备注"},
                },
                "required": ["record_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_record",
            "description": "删除一条记录，删除后无法恢复。程序会在执行前自动向用户确认，调用前不需要先问用户。record_id 要先用 query_records 查出来",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_id": {"type": "integer", "description": "要删除的记录 id"},
                },
                "required": ["record_id"],
            },
        },
    },
     {
        "type": "function",
        "function": {
            "name": "set_budget",
            "description": "设置某个分类的每月预算，已经设置过就覆盖成新金额",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "分类，比如餐饮、交通"},
                    "amount": {"type": "number", "description": "每月预算金额，必须大于0"},
                },
                "required": ["category", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_budgets",
            "description": "列出所有设置了预算的分类，以及本月已花、剩余、是否超支",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

# 工具名 → 真正执行的函数
TOOL_FUNCTIONS = {
    "add_record": add_record,#有括号就直接调用了所以不加
    "query_records": query_records,
    "update_record": update_record,
    "delete_record": delete_record,
    "set_budget": set_budget,
    "list_budgets": list_budgets,
}

NEED_CONFIRM = {"delete_record"}#删除操作是需要确认的
READ_ONLY_TOOLS = {"query_records", "list_budgets"}#哪些工具是只读的
MAX_STEPS = 5#这是chat里的loop循环最多次数，也就是一次请求调用工具最多次数

OMITTED = json.dumps({"note": "旧结果已省略，需要时请重新调用工具查询"}, ensure_ascii=False)#替换旧工具结果的占位文字，也用来判断是否已替换
MAX_TURNS = 10
SUMMARY_PREFIX = "【之前对话的摘要】" #判断是否是摘要就看有没有这个前缀
CONTEXT_MANAGE = True

def shrink_old_tool_results(messages, keep_turns=2):
    """最近 keep_turns 轮之前的 tool 结果换成占位文字，直接修改传进来的列表"""
    user_idx=[]
    for i in range(0, len(messages)):
        if messages[i]["role"]=="user":
            user_idx.append(i)

    if len(user_idx)<=keep_turns:#轮数过少无需省略
        return
    
    boundary=user_idx[-keep_turns]

    for i in range(0, boundary):
        if messages[i]["role"]=="tool" and messages[i]["content"]!=OMITTED:
            messages[i]["content"]=OMITTED


def trim_old_turns(messages, max_turns=MAX_TURNS):
    """只保留 system 和最近 max_turns 轮，直接修改传进来的列表。
    返回被删掉的那些消息（检查点 C 要拿它们做摘要），没删就返回空列表。"""

    user_idx=[]
    for i in range(0, len(messages)):
        if messages[i]["role"]=="user":
            user_idx.append(i)

    if len(user_idx)<=max_turns:
        return []

    boundary=user_idx[-max_turns]
    removed=messages[1:boundary]

    del messages[1:boundary]

    return removed


def summarize_turns(removed):
    """把被裁掉的消息压成一段摘要，返回摘要文字"""

    prev_content=""
    for m in removed:
        if m["role"] in ("system", "user", "assistant") and m["content"]:
            prev_content+=f"{m['role']}: {m['content']}\n" 

    response=client.chat.completions.create(model=MODEL, messages=[{"role": "system", "content": "把下面的对话压缩成几句话，保留人名、金额、日期和用户明确说过的事实"}, 
              {"role": "user", "content": prev_content}])

    usage=response.usage
    if usage is not None:
        logger.info(f"[token-摘要]输入:{usage.prompt_tokens} / 输出:{usage.completion_tokens} / 合计:{usage.total_tokens}")

    return response.choices[0].message.content

def add_summary(messages, removed):
    """把被裁掉的消息压成摘要，插在 system 之后"""

    text=summarize_turns(removed)
    messages.insert(1, {"role": "system", "content": SUMMARY_PREFIX+text})

# ===== 第3段：执行一次工具调用 =====

def run_tool(name, arguments):
    logger.info(f"[调用工具] {name} {arguments}")

    start_time=time.perf_counter()
    try:
        # 有的模型在没有参数时返回空字符串，当成 {} 处理
        args = json.loads(arguments or "{}")# JSON字符串 → 字典
        func = TOOL_FUNCTIONS.get(name)
        if func is None:
            result = {"error": f"没有这个工具：{name}"}
        else:
            result = func(**args)# 把字典拆成关键字参数传进去
    except json.JSONDecodeError:
        logger.error(f"[工具调用错误]{name}参数不是合法的JSON")
        result = {"error": "参数不是合法的JSON，请按说明书的格式重新调用"}
    except TypeError as e:
        logger.error(f"[工具调用错误]{name}参数不对{e}")
        result = {"error": f"参数不对：{e}"}
    except Exception as e:
        logger.error(f"[工具调用错误]{name}工具执行出错{e}")
        result = {"error": f"工具执行出错：{e}"}

    end_time=time.perf_counter()
    use_time=end_time-start_time

    logger.info(f"[工具结果] {name} 耗时 {round(1000*use_time)}ms {result}")
    return json.dumps(result, ensure_ascii=False)# 字典 → JSON字符串 false是保证中文不会被转成 \u5f20 这种编码

def confirm_with_user(args):
    """危险操作执行前，由程序直接问用户。返回 True 表示同意执行"""
    record = get_record(args.get("record_id"))
    if record is None:
        return True  # 记录不存在，交给 delete_record 自己返回"没有这条记录"
    print(f"  [需要确认] 即将删除：#{record['id']} {record['created_at']} "
          f"{record['record_type']} {record['amount']}元 {record['category']} {record['remark']}")
    answer = input("  确认删除？(y/n)：").strip().lower()
    return answer == "y"#answer == "y"本来就是true或者false

# ===== 第4段：处理一轮对话 =====
#chat 遇到删除：不执行，把 tool_call_id、工具名、参数存进便签；这一批调用全部处理完后，带着便签 return
#不能一看到删除就 return：不然一次要调用多个工具其他工具还没用就return了
#resume_chat：执行或取消，然后按 tool_call_id 补上 tool 结果，再调用一次 chat 接着跑
#网页版里，处理 confirm 的循环在 JS 的 while 里；把会话存进库的是 api.py 的 build_response

def chat(messages):
    if CONTEXT_MANAGE:
        #把messages裁剪
        removed=trim_old_turns(messages)
        if removed:
            logger.info(f"[裁剪]删掉{len(removed)}条")
            add_summary(messages, removed)
            logger.info("[摘要]已生成")
        #先把messages瘦身
        shrink_old_tool_results(messages)

    seen=set()

    # 最多和模型来回5次，防止它一直调用工具停不下来
    for _ in range(MAX_STEPS):
        #把会话和工具说明书都发给模型
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools
        )
        #得到的返回message可能是一句话或者要调用工具
        message=response.choices[0].message
        usage=response.usage
        if usage is not None:
            logger.info(f"[token] 输入 {usage.prompt_tokens} / 输出 {usage.completion_tokens} / 合计 {usage.total_tokens}")

        if not message.tool_calls:
            messages.append({"role": "assistant", "content": message.content})#没有工具请求就把回复的话加入messages
            return {"type": "reply", "content": message.content}   #返回字典
        #调用chat的时候就会自动存入messages了
        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in message.tool_calls
            ],
        }) 

        pending = None
        for call in message.tool_calls:
            if call.function.name in NEED_CONFIRM:
                if pending is None:
                    pending={"tool_call_id": call.id, "name": call.function.name, "arguments": call.function.arguments}
                else:
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": {"error": "一次只能删除一条，请等这条处理完再删下一条"}})
            
            else:#don't need confirm
                key=(call.function.name, call.function.arguments)
                if call.function.name in READ_ONLY_TOOLS and key in seen:
                    result=json.dumps({"error": "刚才已用相同参数查询过，结果在上文，请直接根据已有结果回答"}, ensure_ascii=False)
                    logger.info(f"[重复调用]{call.function.name}")
                else:
                    result=run_tool(call.function.name, call.function.arguments)
                    seen.add(key)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)})#放进content里的必须是字符串
        
        if pending is not None:
            return {"type": "confirm", "pending": pending}#type是confirm则会问用户
    #for循环结束
    logger.info("[兜底]已到达最大步数，模型直接回答")
    response=client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        tool_choice="none",
    )
    message=response.choices[0].message
    messages.append({"role": "assistant", "content": message.content})
    return {"type": "reply", "content": message.content}



def resume_chat(messages, pending, approved):#approved是用户同意标志
    if approved:
        result = run_tool(pending["name"], pending["arguments"])        # 从便签上取名字和参数
    else:
        result = json.dumps({"error": "用户取消了这次删除，记录没有删除"}, ensure_ascii=False)

    messages.append({"role": "tool", "tool_call_id": pending["tool_call_id"], "content": result})   # id 也从便签上取
    return chat(messages)


# ===== 第5段：主程序 ===== 
def main():
    init_db()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("记账助手已启动，输入 q 退出")

    while True:
        user_input = input("你：").strip()#去掉首尾空格
        if user_input.lower() == "q":
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        result = chat(messages)

        while result["type"] == "confirm":
            pending = result["pending"]
            args = json.loads(pending["arguments"])              # 提示：confirm_with_user 要的是字典，便签里的参数是字符串
            approved = confirm_with_user(args)   # 打印要删的记录，问 y/n，返回 True 或 False
            result = resume_chat(messages, pending, approved)

        print("助手：", result["content"])




if __name__ == "__main__":
    main()
