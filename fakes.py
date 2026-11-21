from types import SimpleNamespace


def fake_reply(text):
    """伪造模型"直接回复"的返回值"""

    message = SimpleNamespace(content=text, tool_calls=None)   # 最里层：message
    choice = SimpleNamespace(message=message)                  # 包一层：choice.message
    return SimpleNamespace(choices=[choice], usage=None)       # 最外层：choices 是列表，放一个 choice



def fake_tool_call(name, arguments, call_id="call_1"):
    """伪造模型"要调用一个工具"的返回值"""

    function=SimpleNamespace(name=name, arguments=arguments)
    call=SimpleNamespace(function=function, id=call_id)
    message=SimpleNamespace(tool_calls=[call], content=None)
    choice=SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice], usage=None)


class FakeClient:
    """按剧本依次返回预设结果的假 client"""

    def __init__(self, script):
        self.script = list(script)     # 剧本：一个列表，每次 create 被调用就取走第一项
        self.calls = []                # 记下每次 create 收到的参数，测试里可以检查
        # 下面这行是样板：让 client.chat.completions.create 这个调用路径能找到 self.create
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):#真实create会联网返回模型结果，但伪造的就从剧本里取一条结果
        # 1. 拍快照：记下这次收到的所有参数，messages 单独复制一份
        record = dict(kwargs)
        record["messages"] = list(kwargs["messages"])
        self.calls.append(record)#call记录参数

        # 2. 剧本已经用完还被调用，说明 chat 多问了一次模型，直接让测试失败
        if not self.script:
            raise AssertionError("剧本用完了，模型被多调用了一次")

        # 3. 取出剧本的第一条，列表随之变短
        item = self.script.pop(0)

        # 4. 如果这一条是一个异常，就模拟模型出错，把它抛出去（检查点 C 用）
        if isinstance(item, Exception):
            raise item

        # 5. 否则把它当成模型的返回值，交给 chat
        return item