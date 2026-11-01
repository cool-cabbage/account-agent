import os
import db

db.DB_PATH = "test_budget.db"  # 换成测试数据库


if __name__ == "__main__":
    db.init_db()

    print("设预算500：", db.set_budget("餐饮", 500))
    print("改成600：", db.set_budget("餐饮", 600))
    print("负数预算：", db.set_budget("餐饮", -1))
    print("还没花钱：", db.get_budget_status("餐饮"))
    print()
    print("记一笔餐饮：", db.add_record("支出", 25.5, "餐饮", "午饭"))
    print("记一笔交通：", db.add_record("支出", 18, "交通"))
    print("记一笔收入：", db.add_record("收入", 2000, "生活费"))
    print()
    print("没设预算的分类：", db.get_budget_status("娱乐"))
    print("超预算：", db.add_record("支出", 600, "餐饮", "聚餐"))
    print()
    print("全部预算：", db.list_budgets())

    os.remove("test_budget.db")  # 测完删掉
