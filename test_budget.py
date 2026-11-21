import db


def test_set_and_update_budget():
    """第一次设预算没有旧值；再设一次，old_budget 是上一次的金额"""
    first = db.set_budget("餐饮", 500)
    assert first["monthly_budget"] == 500
    assert first["old_budget"] is None

    second = db.set_budget("餐饮", 600)
    assert second["monthly_budget"] == 600
    assert second["old_budget"] == 500


def test_negative_budget():
    """预算金额不合法 → 返回 error"""
    result = db.set_budget("餐饮", -1)
    assert "error" in result


def test_status_before_spending():
    """设了预算还没花钱：已花 0，剩余等于预算"""
    db.set_budget("餐饮", 500)
    status = db.get_budget_status("餐饮")
    assert status["spent"] == 0
    assert status["remaining"] == 500


def test_expense_shows_budget():
    """有预算的分类记支出，返回结果里带预算状态"""
    db.set_budget("餐饮", 500)
    result = db.add_record("支出", 25.5, "餐饮", "午饭")
    assert result["budget"]["remaining"] == 474.5


def test_no_budget_no_status():
    """没设预算的分类记支出，结果里没有 budget"""
    result = db.add_record("支出", 18, "交通")
    assert "budget" not in result


def test_income_no_budget():
    """收入不计入预算：就算这个分类设了预算，结果里也没有 budget"""
    db.set_budget("生活费", 500)
    result = db.add_record("收入", 2000, "生活费")
    assert "budget" not in result


def test_category_without_budget():
    """没设预算的分类，查预算状态返回 None"""
    assert db.get_budget_status("娱乐") is None


def test_over_budget():
    """支出超过预算：over_budget 为 True，剩余是负数"""
    db.set_budget("餐饮", 500)
    result = db.add_record("支出", 600, "餐饮", "聚餐")
    assert result["budget"]["over_budget"] is True
    assert result["budget"]["remaining"] == -100


def test_list_budgets():
    """设了两个分类的预算，list_budgets 返回两条"""
    db.set_budget("餐饮", 500)
    db.set_budget("交通", 100)
    result = db.list_budgets()
    assert len(result["budgets"]) == 2

