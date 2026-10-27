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

if __name__ == "__main__":#测试函数，别的程序import的时候只会拿到之前的内容，不会拿到init_db()
    init_db()
