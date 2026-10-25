import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()#把env里的内容读进来
client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
)

# 工具说明书：外面多包了一层 "type": "function"，参数字段叫 parameters
tools = [
    {
        "type": "function",
        "function": {#字典的第二个，表示功能有哪些
            "name": "add_record",#功能名称
            "description": "记录一笔收入或支出",#功能描述
            "parameters": {#功能的参数有哪些
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["收入", "支出"], "description": "收入还是支出"},
                    "amount": {"type": "number", "description": "金额，单位元"},
                    "category": {"type": "string", "description": "分类，比如餐饮、交通、生活费"},
                    "remark": {"type": "string", "description": "备注"},
                },
                "required": ["type", "amount", "category"],#必填项
            },#参数介绍完毕
        },#功能介绍完毕
    }
]

response = client.chat.completions.create(#给模型发这些，返回的结果保存在response里
    model=os.getenv("MODEL"),#用哪个模型
    tools=tools,
    messages=[{"role": "user", "content": "今天午饭花了25块"}],
)

message = response.choices[0].message#openai库把返回的JSON转成了对象，不是字典所以用'.',message是一个字典但openai库会把整个返回的JSON一层层转成对象
print("停止原因：", response.choices[0].finish_reason)
print("文字回复：", message.content)

if message.tool_calls:#判断有无调用工具
    for call in message.tool_calls:
        print("调用工具：", call.function.name)
        args = json.loads(call.function.arguments)  # 参数是JSON字符串，要转成字典  jsonify 是字典 → JSON（Flask返回给客户端）
        print("参数：", args)                       # json.loads  JSON字符串 → 字典（读取别人发来的JSON）
        
print(response.model_dump_json(indent=2))
