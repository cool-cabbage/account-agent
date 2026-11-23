# 记账 Agent

用自然语言记账、查账、设预算的 AI 助手。自己写了 agent loop，没有用 LangChain 之类的框架，重点处理 loop 的失败路径：删除前暂停等确认、上下文超长、模型超时、死循环、重复调用。

## 功能

- 自然语言记账：「午饭花了20」→ 记一笔餐饮支出
- 查询：按分类、日期查收支，「这个月餐饮花了多少」
- 修改和删除：先查到记录 id 再操作；删除前必须由用户确认
- 每月预算：记账时自动提醒本月已花多少、还剩多少、是否超支
- 网页聊天界面，会话存进数据库，刷新页面或重启服务都不会丢

## 架构

    浏览器（index.html）
       │  POST /chat、POST /chat/confirm
       ▼
    api.py  ── 会话读写、HTTP 状态码、503 处理
       │
       ▼
    agent.py ── agent loop：问模型 → 执行工具 → 结果交回模型
       │            上下文管理、步数兜底、重复检测、日志
       ▼
    db.py   ── SQLite：records / budgets / sessions 三张表

- db.py 只管数据，不知道有模型
- agent.py 只管 loop，命令行和网页用的是同一个 chat()
- api.py 只管 HTTP，不直接调用模型，也不写 SQL

## agent loop 的失败处理

| 问题 | 处理方式 |
|---|---|
| 删除不可逆 | 遇到 delete_record 先不执行，存一张"便签"（tool_call_id、工具名、参数）后退出 loop；用户确认后由 resume_chat 补上 tool 结果、接着跑。确认由代码按 true/false 判断，不交给模型理解 |
| tool_calls 必须配对 | 暂停、拒绝、"一次只能删一条"、重复调用拦截，每个 tool_call 都会补一条 tool 结果，否则 API 会报错 |
| 工具调用出错 | 坏 JSON、参数名错误、工具不存在、业务校验失败，都返回 error 交给模型修正，不让程序崩溃 |
| 上下文越来越长 | ① 最近 2 轮之前的工具结果换成"已省略"占位，模型需要时重新查询，也避免凭旧 id 回答；② 超过 10 轮按轮裁剪，切口一定落在 user 消息上，不拆散 tool_calls 和结果；③ 裁掉的内容由模型压成摘要，插在 system 之后 |
| 死循环 | 最多问模型 5 次；用完后带 tool_choice="none" 再问一次，逼模型根据已有信息回答 |
| 重复查询 | 同一次 chat 里，只读工具用相同参数第二次调用时不执行，提醒模型结果已在上文。写操作不拦截（"记两笔各10元"是合法的） |
| 模型超时或断网 | SDK 设 60 秒超时、重试 2 次；仍失败则接口返回 503，本轮会话不写回数据库，用户可直接重发 |
| 排查问题 | logging 同时输出到终端和 agent.log，记录每次工具调用、耗时、token 用量和错误 |

## 实测数据
- 上下文管理开 / 关对比（测试时 MAX_TURNS=3，同样 8 句话，每句第 1 次调用模型的输入 token）：

| 句子 | 关闭 | 打开 |
|---|---|---|
| 1 | 1425 | 1425 |
| 4 | 1871 | 1831 |
| 8 | 3082 | 1859 |

- 第 8 句输入降低约 40%，打开后单次输入稳定在 1800～2300，不再随轮数增长；两种情况下模型都还记得第 1 句里的名字
- 8 句总消耗：关闭约 32200，打开约 30450（含 5 次摘要调用共 2926），只省约 5%。短对话里摘要本身有开销，对话越长省得越多
- 改进方向：摘要 prompt 限定字数；超限后一次多裁几轮，减少摘要次数；摘要改用不带思考的模型

## 测试

20 个 pytest 测试，每个测试用一个临时数据库，不碰真实数据；用按剧本返回的假模型代替真实 API，不联网、不花钱，结果稳定可复现。

- test_run_tool.py：坏 JSON、参数错误、工具不存在、负金额、记账后查询
- test_agent_loop.py：直接回复、调工具再回复、跑满步数兜底、重复查询拦截、删除暂停与取消后的配对
- test_api.py：模型超时返回 503，且会话不写回
- test_budget.py：预算设置、超支、收入不计入预算等

运行：

    python -m pytest -v

## 运行

    git clone https://github.com/cool-cabbage/account-agent.git
    cd account-agent
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env      # 填入自己的 API_KEY、BASE_URL、MODEL
    uvicorn api:app --reload

浏览器打开 http://127.0.0.1:8000/ 。命令行版：python agent.py

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /chat | {message, session_id?} → type 为 reply 或 confirm |
| POST | /chat/confirm | {session_id, approved} → 执行或取消删除 |
| GET | /records | 查询参数 record_type、category、start_date、end_date |
| POST | /records | 新增一条，返回 201 |
| PATCH | /records/{id} | 只改传入的字段 |
| DELETE | /records/{id} | 删除 |
| GET | /budgets | 预算列表 |
| GET | /health | 健康检查 |

返回 type 的约定：reply 是普通回复；confirm 表示有待确认的删除，前端要弹窗，再调用 /chat/confirm。

## 已知限制和改进方向

- **没有鉴权**：只适合本机运行，部署前要加登录和接口限流
- **多用户数据不隔离**：session_id 只隔离对话，账本是共用的。多人使用需要给三张表加 user_id 并按用户过滤查询；目前给他人试用的做法是单独起一份服务、用单独的数据库文件，并加访问口令和每日次数上限
- **金额用 float 存**：小数有精度误差，正确做法是用整数"分"或 Decimal
- **确认接口防连点**：两个确认请求同时到达时，可能都读到同一张便签。改进：用 `UPDATE ... WHERE pending IS NOT NULL` 加 rowcount 原子认领
- **便签不过期**：用户一直不确认，会话会一直被 409 拦住。改进：便签记录创建时间，超时自动取消
- **部分失败**：记账已成功但生成回复时超时，用户重发会重复记账。改进：前端给每条消息带请求编号，服务器去重
- **同一会话并发**：两个请求同时读写同一会话，后写的会覆盖先写的。改进：加版本号或按会话排队
- **刷新后聊天区为空**：模型仍记得历史，但页面没有显示历史的接口

## 部署思路（未实操）

用 uvicorn 多进程或 gunicorn 运行，前面加 Nginx 做 HTTPS 和反向代理；.env 通过服务器环境变量注入，不进仓库；SQLite 并发写有限，用户多了换成 PostgreSQL。

## 技术栈

Python、FastAPI、Pydantic、SQLite、OpenAI SDK（兼容接口）、pytest、原生 HTML/JS
