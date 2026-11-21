import json
from agent import run_tool


def test_bad_json():
    """参数不是合法 JSON → 返回 error"""
    result=json.loads(run_tool("query_records", "abc"))#run_tool里第二个参数是call发来的json字符串
    assert "参数不是合法的" in result["error"]

def test_wrong_args():
    """参数名不对，比如给 list_budgets 传 {"x": 1} → 返回 error，提示参数不对"""
    result=json.loads(run_tool("delete_record", '{"id": "bb"}'))
    assert "参数不对" in result["error"]

def test_unknown_tool():
    """调用不存在的工具 → 返回 error，提示没有这个工具"""
    result=json.loads(run_tool("abc", '{"re": "aaa"}'))
    assert "没有这个工具" in result["error"]


def test_negative_amount():
    """add_record 金额是负数 → 返回 error"""
    result=json.loads(run_tool("add_record", '{"record_type": "收入", "amount": -18, "category": "餐饮"}'))
    assert "金额" in result["error"]

def test_add_then_query():
    """记一笔账，再用 query_records 查，count 应该正好是 1"""
    run_tool("add_record", '{"record_type": "支出", "amount": 18, "category": "餐饮"}')
    row=json.loads(run_tool("query_records", '{}'))
    assert row["count"]==1