import pytest
import db
import api


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """每个测试都用一个全新的临时数据库"""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))   # 把 DB_PATH 暂时替换成临时库
    db.init_db()


@pytest.fixture(autouse=True)
def no_access_control(monkeypatch):
    """测试不受终端里 APP_PASSWORD 和每日次数的影响"""
    monkeypatch.setattr(api, "APP_PASSWORD", None)        # 关掉口令检查
    monkeypatch.setitem(api.chat_count, "date", None)     # 次数从 0 开始算
    monkeypatch.setitem(api.chat_count, "count", 0)

