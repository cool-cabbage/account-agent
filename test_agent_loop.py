import agent
import db
import json
from agent import chat, resume_chat, SYSTEM_PROMPT
from fakes import FakeClient, fake_reply, fake_tool_call


def new_messages(text):
    """造一段刚开始的对话：system + 一条 user"""
    # 返回一个列表，两条消息，格式和 main 里一样
    return [{
        "role": "system", "content": SYSTEM_PROMPT
    },
    {
        "role": "user", "content": text
    }]

def assert_paired(messages):
    """检查每个 tool_call 都有对应的 tool 结果，反过来每条 tool 结果也都有对应的 tool_call"""

    call_ids = set()#assistant的toolcall
    result_ids = set()#tool执行的tool_call_id
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):#是模型回复的有工具请求的信息
            for call in m["tool_calls"]:#请求的每一个工具
                call_ids.add(call["id"])

        if m["role"] == "tool":
            result_ids.add(m["tool_call_id"])
    assert call_ids == result_ids



def test_direct_reply(monkeypatch):
    """模型直接回复：chat 返回 reply，只调用一次模型"""

    fake=FakeClient([fake_reply("你好")])#fake_reply("你好")相当于是造的的剧本，直接传进__init__里
    monkeypatch.setattr(agent, "client", fake)
    messages=new_messages("你好")
    result=chat(messages)#此时chat里已经是fake了，所以返回的是剧本里的结果

    assert result["type"]=="reply"
    assert result["content"]=="你好"
    assert len(fake.calls)==1
    assert messages[-1]["role"]=="assistant"

def test_tool_then_reply(monkeypatch):
    """模型先调 add_record 再回复：数据库里多一笔，配对完整，第二次调用模型时已经能看到工具结果"""
    fake = FakeClient([
        fake_tool_call("add_record", '{"record_type": "支出", "amount": 8, "category": "餐饮"}'),
        fake_reply("记好了"),
    ])
    monkeypatch.setattr(agent, "client", fake)
    messages = new_messages("早饭花了8")
    result = chat(messages)

    assert result["type"]=="reply"
    assert len(fake.calls)==2
    assert db.query_records()["count"]==1
    assert_paired(messages)
    assert fake.calls[1]["messages"][-1]["role"]=="tool"

def test_max_steps_fallback(monkeypatch):
    """步数用完后，不带工具再问一次模型，返回兜底回复"""
    monkeypatch.setattr(agent, "MAX_STEPS", 2)
    fake = FakeClient([
        fake_tool_call("query_records", '{"category": "餐饮"}', call_id="call_1"),
        fake_tool_call("query_records", '{"category": "交通"}', call_id="call_2"),
        fake_reply("兜底回答"),
    ])
    monkeypatch.setattr(agent, "client", fake)
    messages = new_messages("这个月花了多少")
    result = chat(messages)

    assert result["type"]=="reply"
    assert result["content"]=="兜底回答"
    assert len(fake.calls)==3
    assert fake.calls[-1]["tool_choice"]=="none"#兜底回答的calls里会有这个tool_choice = none
    assert_paired(messages)

def test_duplicate_query_blocked(monkeypatch):
    """相同参数的第二次查询不执行，返回提醒"""
    fake = FakeClient([
        fake_tool_call("query_records", '{"category": "餐饮"}', call_id="call_1"),
        fake_tool_call("query_records", '{"category": "餐饮"}', call_id="call_2"),
        fake_reply("好的"),
    ])
    monkeypatch.setattr(agent, "client", fake)
    messages = new_messages("查一下餐饮")
    chat(messages)

    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert len(tool_msgs)==2
    assert "count" in tool_msgs[0]["content"]
    assert "相同参数" in tool_msgs[1]["content"]

def test_delete_pause_and_cancel(monkeypatch):
    """chat 遇到删除就暂停；resume_chat 传 False 后补上配对，记录还在"""
    record = db.add_record("支出", 8, "餐饮")         # 先在临时库里记一笔，拿到它的 id
    rid = record["id"]
    fake = FakeClient([
        fake_tool_call("delete_record", json.dumps({"record_id": rid}), call_id="call_del"),
        fake_reply("已保留"),
    ])
    monkeypatch.setattr(agent, "client", fake)
    messages = new_messages("删掉那笔")

    result = chat(messages)
    assert result["type"]=="confirm"
    assert result["pending"]["tool_call_id"]=="call_del"
    assert messages[-1]["role"]=="assistant"
    assert messages[-1]["tool_calls"][0]["id"] == "call_del"#检查最后一条是不是未配对的消息

    result2 = resume_chat(messages, result["pending"], False)
    assert result2["type"]=="reply"
    assert db.get_record(rid) is not None
    assert_paired(messages)