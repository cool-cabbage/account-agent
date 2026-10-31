import sqlite3
from datetime import datetime

DB_PATH = "records.db"

def get_db():#连接数据库，sqlite3可以让查询结果可通过dict转化为字典
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():#建表已存在就跳过
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_type TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            remark TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def list_records():#查询所有记录
    conn = get_db()
    rows = conn.execute("SELECT * FROM records ORDER BY id").fetchall()#fetchall是为了把数据取出来，不然只能得到游标，数据库关闭后就得不到数据了
    conn.close()
    return [dict(row) for row in rows]

def add_record(record_type, amount, category, remark=""):#remark不传就默认为空字符串
    """记一笔账。参数不合法时返回 {"error": ...}，成功时返回这条记录"""

    if record_type  != "收入" and record_type != "支出":
        return {"error": "类型只能是收入或支出"}

    if amount <= 0:
        return {"error": "金额必须大于0"}

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_db()

    cursor = conn.execute("INSERT INTO records (record_type, amount, category, remark, created_at) VALUES (?, ?, ?, ?, ?)", (record_type, amount, category, remark, created_at))
    new_id = cursor.lastrowid#lastrowid是一个值不加括号
    conn.commit()
    conn.close()

    return {"id": new_id, "record_type": record_type, "amount": amount, "category": category, "remark": remark, "created_at": created_at}
    #return所有数据的原因是要返回给大模型，大模型要知道你存了些什么才好给你交代


def query_records(record_type=None, category=None, start_date=None, end_date=None):
    """按条件查询记录。参数都可以不填，不填就是不限制"""#主要是方便用户想通过什么查询都可以
    conditions = []#WHERE 后面接的参数=？
    params = []#放参数

    if record_type:
        conditions.append("record_type = ?")
        params.append(record_type)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if start_date:
        conditions.append("date(created_at) >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date(created_at) <= ?")
        params.append(end_date)

    sql = "SELECT * FROM records"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id"

    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    records = [dict(row) for row in rows]


    count = len(records)
    income_total = 0
    expense_total = 0
    for record in records :
        if record["record_type"] == "收入":
            income_total += record["amount"]
        elif record["record_type"] == "支出":
            expense_total += record["amount"]

    return {
        "count": count,
        "income_total": income_total,
        "expense_total": expense_total,
        "records": records[-20:],
    }

def delete_record(record_id):
    """删除一条记录。不存在时返回 error，成功时返回被删掉的那条"""
    conn = get_db()
    
    row = conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    
    if row is None:
        conn.close()
        return {"error": "没有这条记录"}

    conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()

    return {"deleted": dict(row)}

def update_record(record_id, record_type=None, amount=None, category=None, remark=None):
    """修改一条记录。只改传进来的字段，没传的不动"""

    if record_type is not None and record_type not in ("收入", "支出"):
        return {"error": "类型必须为收入或支出"}

    if amount is not None and amount <= 0:
        return {"error": "金额需大于零"}

    

    fields = []
    params = []
    if record_type is not None:
        fields.append("record_type = ?")
        params.append(record_type)
    if amount is not None:
        fields.append("amount = ?")
        params.append(amount)
    if category is not None:
        fields.append("category = ?")
        params.append(category)
    if remark is not None:
        fields.append("remark = ?")
        params.append(remark)

    if not fields:
        return {"error": "没有要修改的内容"}

    params.append(record_id)  # 最后一个 ? 是 WHERE id = ?，所以 id 放在最后
    sql = "UPDATE records SET " + ", ".join(fields) + " WHERE id = ?"#update是用，连接不用AND+

    conn = get_db()
    cursor = conn.execute(sql, params)

    if cursor.rowcount == 0:
        conn.close()#返回前都必须关闭数据库
        return{"error": "没有这条记录"}
    
    conn.commit()
    row = conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    conn.close()
    return dict(row)

def get_record(record_id):
    """按 id 取一条记录。找到返回字典，找不到返回 None"""
    conn = get_db()
    row = conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    conn.close()
    if not row:
        return None
    else:
        return dict(row)
     


def print_result(title, result):
    """测试用：先打印汇总，再把每条记录分行打印"""
    print(f"===== {title} =====")
    print(f"笔数：{result['count']}  收入：{result['income_total']}  支出：{result['expense_total']}")
    for record in result["records"]:
        print(f"  #{record['id']} {record['created_at']} {record['record_type']} "#双引号里面要用单引号
              f"{record['amount']}元 {record['category']} {record['remark']}")
    print()

if __name__ == "__main__":
    init_db()
    print_result("全部", query_records())


