import httpx
import openai
from fastapi.testclient import TestClient
import agent
import db
from api import app
from fakes import FakeClient, fake_reply


def test_model_timeout_returns_503(monkeypatch):
    """第二句模型超时 → 503，并且这一句没写进会话"""
    timeout = openai.APITimeoutError(request=httpx.Request("POST", "https://fake")) #造了一个超时对象
    fake = FakeClient([fake_reply("记住了"), timeout])   # 第1次正常回复，第2次create取出的是timeout，就会把它抛出
    monkeypatch.setattr(agent, "client", fake)
    api_client = TestClient(app)

    r1 = api_client.post("/chat", json={"message": "我叫大白菜"})#相当于在docs里发一次/chat
    print(r1.status_code, r1.json())

    sid = r1.json()["session_id"]
    r2 = api_client.post("/chat", json={"message": "我叫什么", "session_id": sid})

    assert r1.status_code==200
    assert r2.status_code==503#503是那个timeout
    assert len(db.load_session(sid)["messages"])==3
    # 检查1：r1 的状态码是 200
    # 检查2：r2 的状态码是 503
    # 检查3：库里这个会话只有 3 条消息（system、第一句 user、第一句 assistant）
    #        提示：db.load_session(sid)["messages"]，第二句没写回，所以不是 5 条
