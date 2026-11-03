from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from db import init_db, list_budgets, query_records, add_record, update_record, delete_record, get_record

app = FastAPI(title="记账 Agent API")   # 样板：创建那张"网址 → 函数"的表 fastapi做的就是查表调函数转JSON

#2：建表。提示见下面
init_db()


@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/budgets")
def get_budgets():
    return list_budgets()

@app.get("/records")
def get_records(record_type: str | None = None, category: str | None = None, start_date: str | None = None, end_date: str | None = None):
#参数是字符串或None或不传默认None
    return query_records(record_type=record_type, category=category, start_date=start_date, end_date=end_date)
    # 用关键字传参 record_type=record_type 更稳，
    # 这样就算以后 query_records 的参数顺序变了也不会传错

#继承了 BaseModel 之后，构造函数和类型检查 Pydantic 都替你做好了
class RecordIn(BaseModel):
    record_type: str
    amount: float
    category: str
    remark: str = ""



@app.post("/records", status_code=201)    # 样板：新建成功返回 201，而不是默认的 200
def create_record(record: RecordIn):

    result = add_record(**record.model_dump())

    if "error" in result:
        raise HTTPException(status_code = 400, detail=result["error"])

    return result


#   提示：update_record 是用 is not None 判断有没有传的，所以 None 正好表示"不改"
class RecordUpdate(BaseModel):
    record_type: str | None = None
    amount: float | None = None
    category: str | None = None
    remark: str | None = None


@app.patch("/records/{record_id}")
def modify_record(record_id: int, data: RecordUpdate):

    if get_record(record_id) is None:
        raise HTTPException(status_code=404, detail="找不到该记录")

    result = update_record(record_id, **data.model_dump())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@app.delete("/records/{record_id}")
def remove_record(record_id: int):

    result = delete_record(record_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result