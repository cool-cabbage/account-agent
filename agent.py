import os
import json
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from db import init_db, add_record, query_records

load_dotenv()
client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
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
9. 回答简洁，用中文。"""

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
]

# 工具名 → 真正执行的函数
TOOL_FUNCTIONS = {
    "add_record": add_record,#有括号就直接调用了所以不加
    "query_records": query_records,
}


# ===== 第3段：执行一次工具调用 =====
def run_tool(call):
    name = call.function.name
    args = json.loads(call.function.arguments)  # JSON字符串 → 字典
    print(f"  [调用工具] {name} {args}")

    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        result = {"error": f"没有这个工具：{name}"}
    else:
        result = func(**args)  # 把字典拆成关键字参数传进去

    print(f"  [工具结果] {result}")
    return json.dumps(result, ensure_ascii=False)  # 字典 → JSON字符串 false是保证中文不会被转成 \u5f20 这种编码



# ===== 第4段：处理一轮对话 =====
def chat(messages):
    # 最多和模型来回5次，防止它一直调用工具停不下来
    for _ in range(5):#'_'表示i，但这个循环用不到
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
        )
        message = response.choices[0].message

        # 情况1：模型不调用工具，直接回复 → 这一轮结束
        if not message.tool_calls:
            messages.append({"role": "assistant", "content": message.content})
            return message.content

        # 情况2：模型想调用工具
        # 先把"模型想调用什么"这条消息加进对话
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
        # 再逐个执行，把结果加进对话
        for call in message.tool_calls:
            result = run_tool(call)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        # 回到循环开头，带着工具结果再问一次模型

    return "工具调用次数太多，已停止。"


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
        reply = chat(messages)
        print("助手：", reply)



if __name__ == "__main__":
    main()
