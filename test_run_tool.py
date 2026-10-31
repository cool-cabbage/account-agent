import os
import json
from types import SimpleNamespace

import db
db.DB_PATH = "test_records.db"  # 换成测试数据库，不动你的真实数据

from agent import run_tool


def fake_call(name, arguments):
    """造一个假的工具调用，结构和模型返回的 call 一样"""
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


def run(title, name, arguments):
    print(f"===== {title} =====")
    run_tool(fake_call(name, arguments))
    print()


if __name__ == "__main__":
    db.init_db()

    run("正常记账", "add_record",
        json.dumps({"record_type": "支出", "amount": 25, "category": "餐饮"}, ensure_ascii=False))
    run("参数名写错", "add_record",
        json.dumps({"type": "支出", "amount": 25, "category": "餐饮"}, ensure_ascii=False))
    run("金额是字符串", "add_record",
        json.dumps({"record_type": "支出", "amount": "25", "category": "餐饮"}, ensure_ascii=False))
    run("JSON格式坏了", "add_record", '{"record_type": "支出", "amount": 25')
    run("空参数查询", "query_records", "")
    run("不存在的工具", "send_money", "{}")
    run("删除，输入 n", "delete_record", '{"record_id": 1}')
    run("删除，输入 y", "delete_record", '{"record_id": 1}')

    os.remove("test_records.db")  # 测完删掉测试数据库
