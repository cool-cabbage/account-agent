import pytest
import db

@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """每个测试都用一个全新的临时数据库"""

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))#把DB_PATH暂时替换成tmp_path
    db.init_db()
