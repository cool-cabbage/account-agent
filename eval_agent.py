"""记账 Agent 评测：只看模型第一步的决策（调哪个工具、参数对不对），不执行工具，不写数据库"""
import json
import logging
from datetime import date, timedelta

import openai
import agent

logging.getLogger("httpx").setLevel(logging.WARNING)   # 评测时不打印每次 HTTP 请求

# ===== 日期：按运行当天自动算，和 SYSTEM_PROMPT 里的"今天"一致 =====
TODAY = date.today()
Y = TODAY.year


def day(offset=0):
    """今天往前或往后 offset 天，比如 day(-1) 是昨天"""
    return (TODAY + timedelta(days=offset)).isoformat()


MONTH_START = TODAY.replace(day=1).isoformat()
_next_month = (TODAY.replace(day=28) + timedelta(days=4)).replace(day=1)
MONTH_END = (_next_month - timedelta(days=1)).isoformat()
_this_monday = TODAY - timedelta(days=TODAY.weekday())
LAST_WEEK_START = (_this_monday - timedelta(days=7)).isoformat()
LAST_WEEK_END = (_this_monday - timedelta(days=1)).isoformat()


# ===== 评测用例 =====
# calls：应该调哪些工具；空列表表示不该调工具，应该追问用户
# args：只写要检查的字段；值写成列表表示命中其中一个就算对
CASES = [
    # 记账
    {"id": 1, "tag": "记账", "input": "午饭花了20",
     "calls": [{"name": "add_record", "args": {"record_type": "支出", "amount": 20, "category": "餐饮"}}]},
    {"id": 2, "tag": "记账", "input": "打车回学校18",
     "calls": [{"name": "add_record", "args": {"record_type": "支出", "amount": 18, "category": "交通"}}]},
    {"id": 3, "tag": "记账", "input": "买了个耳机199",
     "calls": [{"name": "add_record", "args": {"record_type": "支出", "amount": 199, "category": "购物"}}]},
    {"id": 4, "tag": "记账", "input": "看电影花了45",
     "calls": [{"name": "add_record", "args": {"record_type": "支出", "amount": 45, "category": "娱乐"}}]},
    {"id": 5, "tag": "记账", "input": "收到生活费2000",
     "calls": [{"name": "add_record", "args": {"record_type": "收入", "amount": 2000, "category": "生活费"}}]},
    {"id": 6, "tag": "记账", "input": "工资到账3500",
     "calls": [{"name": "add_record", "args": {"record_type": "收入", "amount": 3500, "category": "工资"}}]},
    {"id": 7, "tag": "中文数字", "input": "午饭二十五块",
     "calls": [{"name": "add_record", "args": {"record_type": "支出", "amount": 25, "category": "餐饮"}}]},
    {"id": 8, "tag": "记账", "input": "奶茶12.5",
     "calls": [{"name": "add_record", "args": {"record_type": "支出", "amount": 12.5, "category": "餐饮"}}]},

    # 一句话记多笔
    {"id": 9, "tag": "多笔", "input": "早饭8块，午饭15",
     "calls": [{"name": "add_record", "args": {"amount": 8, "category": "餐饮"}},
               {"name": "add_record", "args": {"amount": 15, "category": "餐饮"}}]},
    {"id": 10, "tag": "多笔", "input": "打车20，奶茶10",
     "calls": [{"name": "add_record", "args": {"amount": 20, "category": "交通"}},
               {"name": "add_record", "args": {"amount": 10, "category": "餐饮"}}]},
    {"id": 11, "tag": "多笔", "input": "今天坐地铁花了4块，晚上又打车花了30",
     "calls": [{"name": "add_record", "args": {"amount": 4, "category": "交通"}},
               {"name": "add_record", "args": {"amount": 30, "category": "交通"}}]},

    # 查询和日期换算
    {"id": 12, "tag": "查询-日期", "input": "这个月餐饮花了多少",
     "calls": [{"name": "query_records", "args": {"category": "餐饮", "start_date": MONTH_START,
                                                  "end_date": [day(), MONTH_END]}}]},
    {"id": 13, "tag": "查询-日期", "input": "今天花了多少",
     "calls": [{"name": "query_records", "args": {"start_date": day(), "end_date": day()}}]},
    {"id": 14, "tag": "查询-日期", "input": "昨天花了多少",
     "calls": [{"name": "query_records", "args": {"start_date": day(-1), "end_date": day(-1)}}]},
    {"id": 15, "tag": "查询-日期", "input": "上周交通花了多少",
     "calls": [{"name": "query_records", "args": {"category": "交通", "start_date": LAST_WEEK_START,
                                                  "end_date": LAST_WEEK_END}}]},
    {"id": 16, "tag": "查询-日期", "input": "这个月收入多少",
     "calls": [{"name": "query_records", "args": {"record_type": "收入", "start_date": MONTH_START,
                                                  "end_date": [day(), MONTH_END]}}]},
    {"id": 17, "tag": "查询", "input": "列出最近的记录",
     "calls": [{"name": "query_records", "args": {}}]},
    {"id": 18, "tag": "查询-日期", "input": "10月一共花了多少",
     "calls": [{"name": "query_records", "args": {"start_date": f"{Y}-10-01", "end_date": f"{Y}-10-31"}}]},
    {"id": 19, "tag": "查询-日期", "input": "前天买了什么",
     "calls": [{"name": "query_records", "args": {"start_date": day(-2), "end_date": day(-2)}}]},

    # 预算
    {"id": 20, "tag": "预算", "input": "餐饮每月预算500",
     "calls": [{"name": "set_budget", "args": {"category": "餐饮", "amount": 500}}]},
    {"id": 21, "tag": "预算", "input": "把交通预算改成150",
     "calls": [{"name": "set_budget", "args": {"category": "交通", "amount": 150}}]},
    {"id": 22, "tag": "预算", "input": "预算还剩多少",
     "calls": [{"name": "list_budgets", "args": {}}]},
    {"id": 23, "tag": "预算", "input": "我餐饮超支了吗",
     "calls": [{"name": "list_budgets", "args": {}}]},

    # 修改、删除：第一步应该先查记录 id
    {"id": 24, "tag": "改删先查", "input": "把今天午饭那笔改成25块",
     "calls": [{"name": "query_records", "args": {"start_date": day(), "end_date": day()}}]},
    {"id": 25, "tag": "改删先查", "input": "把11月1日那笔吃饭删了",
     "calls": [{"name": "query_records", "args": {"start_date": f"{Y}-11-01", "end_date": f"{Y}-11-01"}}]},
    {"id": 26, "tag": "改删先查", "input": "删掉昨天打车那笔",
     "calls": [{"name": "query_records", "args": {"start_date": day(-1), "end_date": day(-1)}}]},

    # 信息不够：应该追问，不能编
    {"id": 27, "tag": "追问", "input": "今天吃饭花了点钱", "calls": []},
    {"id": 28, "tag": "追问", "input": "帮我设个预算300", "calls": []},
    {"id": 29, "tag": "追问", "input": "记一笔", "calls": []},
    {"id": 30, "tag": "追问", "input": "我花了钱", "calls": []},

    # TODO：你补 10 条，id 从 31 开始
]


# ===== 判断规则 =====
def value_ok(expected, actual):
    """expected 是列表时，命中其中任意一个就算对；数字按数值比较（20 和 20.0 算相同）"""
    options = expected if isinstance(expected, list) else [expected]
    for opt in options:
        if isinstance(opt, (int, float)) and isinstance(actual, (int, float)):
            if abs(opt - actual) < 1e-9:
                return True
        elif opt == actual:
            return True
    return False


def args_ok(expected_args, actual_args):
    """只检查标注里写了的字段，没写的（比如 remark）不检查"""
    return all(k in actual_args and value_ok(v, actual_args[k]) for k, v in expected_args.items())


def match_calls(expected, actual):
    """返回 (工具选对了吗, 参数也全对了吗)。多笔调用和顺序无关"""
    if sorted(c["name"] for c in expected) != sorted(c["name"] for c in actual):
        return False, False
    remaining = list(actual)
    for exp in expected:
        hit = next((a for a in remaining
                    if a["name"] == exp["name"] and args_ok(exp.get("args", {}), a["args"])), None)
        if hit is None:
            return True, False
        remaining.remove(hit)       # 一个实际调用只能匹配一个标注，"两笔都是餐饮"时不会重复算
    return True, True


# ===== 问模型第一步 =====
def first_step(text):
    """只问一次模型，返回它想调的工具列表和文字回复"""
    messages = [{"role": "system", "content": agent.SYSTEM_PROMPT},
                {"role": "user", "content": text}]
    response = agent.client.chat.completions.create(model=agent.MODEL, messages=messages, tools=agent.tools)
    msg = response.choices[0].message
    calls = []
    for c in msg.tool_calls or []:
        try:
            args = json.loads(c.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {"_bad_json": c.function.arguments}
        calls.append({"name": c.function.name, "args": args})
    return calls, msg.content


def main():
    results = []
    for case in CASES:
        error = None
        try:
            actual, reply = first_step(case["input"])
        except openai.APIError as e:
            actual, reply, error = [], None, str(e)
        tool_ok, all_ok = match_calls(case["calls"], actual) if error is None else (False, False)
        results.append({**case, "actual": actual, "reply": reply, "error": error,
                        "tool_ok": tool_ok, "all_ok": all_ok})
        mark = "PASS" if all_ok else ("参数错" if tool_ok else "工具错")
        shown = actual if actual else f"（文字）{(reply or error or '')[:40]}"
        print(f"[{mark}] #{case['id']} {case['tag']}｜{case['input']} → {shown}")

    n = len(results)
    should_call = [r for r in results if r["calls"]]
    should_ask = [r for r in results if not r["calls"]]
    print("\n===== 汇总 =====")
    print(f"工具选择准确率：{sum(r['tool_ok'] for r in results)}/{n} = {sum(r['tool_ok'] for r in results) / n:.0%}")
    if should_call:
        k = sum(r["all_ok"] for r in should_call)
        print(f"参数准确率（应调工具的 {len(should_call)} 条）：{k}/{len(should_call)} = {k / len(should_call):.0%}")
    if should_ask:
        k = sum(r["tool_ok"] for r in should_ask)
        print(f"该追问时没乱调工具：{k}/{len(should_ask)}")

    print("\n===== 按类别 =====")
    for tag in sorted({r["tag"] for r in results}):
        group = [r for r in results if r["tag"] == tag]
        print(f"{tag}：{sum(r['all_ok'] for r in group)}/{len(group)}")

    with open("eval_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n详细结果已写入 eval_results.json")


if __name__ == "__main__":
    main()
