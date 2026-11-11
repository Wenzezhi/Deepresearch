# 深度研究助手 · 小组共享版

基于 Datawhale Hello Agents chapter14 的深度研究项目，包含当前 P0/P1 的前后端实现。
这是源码共享版，不是桌面安装包。原有研究、聊天、笔记和标注通过脱敏快照分享，之后各电脑独立保存数据。

## 目录

```text
frontend/                 Vue 前端源码、依赖清单与锁文件
backend/                  Python 后端源码、测试、依赖与配置示例
shared-data/history.json  脱敏历史快照（不是运行数据库）
shared-data/notes/        研究过程笔记及索引
scripts/import-history.py 历史导入工具（只用 Python 标准库）
scripts/test_import_history.py 导入回归验证
start-local.cmd / start-local.ps1 启动前后端
stop-local.cmd / stop-local.ps1   停止前后端
```

## 首次安装（Windows PowerShell）

建议安装 Python 3.11、Node.js 22 和 Git。开发机验证环境为 Python 3.11.3、Node.js 22.17.0。
克隆仓库后，进入本 README 所在目录，运行：

```powershell
py -3.11 -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.local.txt
npm.cmd --prefix frontend ci
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local
.\backend\.venv\Scripts\python.exe scripts/import-history.py
```

如果没有 `py` 启动器，可以用已安装的 Python 3.11 的 `python -m venv backend/.venv`。
不要用 `Copy-Item` 覆盖已有的真实配置。安装依赖需要联网；不要复制别人的虚拟环境。

## 配置与启动

1. 在 `backend/.env` 中填写自己的 `TAVILY_API_KEY`（研究联网搜索需要）。
2. 执行 ` .\start-local.cmd `，或双击它。启动脚本仅监听本机，不需要防火墙放行。
3. 打开 http://127.0.0.1:5174/ 。
4. 首页右侧选择导入的模型配置，点击“修改”，填写自己的 API 地址、模型 ID、API Key，保存并测试连接。也可以新增配置。
5. 选择可用模型后开始研究或聊天。

导入的模型名称和 ID 为历史配置，不保证与你的服务匹配；**所有密钥均为空**。
已导入的配置优先于 `.env` 默认模型，单独填写 `LLM_API_KEY` 不会补齐导入配置的密钥。
未导入历史时，`.env` 的模型配置会在首次启动时用于创建默认配置。
只查看历史无需模型密钥；新研究/聊天仍会调用远程模型，内容会发送给所选服务。

关闭服务：` .\stop-local.cmd `。窗口关闭不等于后台服务停止。
日志位于 `.runtime/`，后端健康检查为 http://127.0.0.1:8000/healthz 。
若 5174 或 8000 已被另一份项目占用，请先停止那份项目，再启动本副本。

## 历史快照与本地数据

快照包含 4 条研究、150 条研究事件、1 个现存全局对话、1 篇用户笔记、3 条阅读对象（含标注/旧式聊天数据），
以及 57 个研究笔记/索引文件。另保留 4 个已删除对话的标识，防止旧聊天迁移后重新出现；其中不包含已删除对话正文。
模型配置共 2 条，密钥已清空。数据统计针对导出时刻。

执行导入后，运行数据库在 `backend/data/research.sqlite3`，研究笔记在 `backend/notes/`。
请在后端停止时导入。路径占位符会转换为当前项目路径，原电脑路径无需存在。
导入脚本不会覆盖已有同 ID 的研究、对话、笔记或模型；已有研究也不会被附加旧事件。
同一快照重复导入会跳过，不会恢复本地已经删除的记录；新产生的记录不受影响。
若使用自定义数据库位置，可用 `--db <路径>`，同时确保后端 `RESEARCH_DB_PATH` 指向同一文件。
此工具是首次共享数据的导入工具，不提供多人数据库合并或云端同步。

## Git 协作

提交源码、锁文件、配置模板、shared-data、scripts 和说明文档。
不要提交真实 `.env`、原始数据库、`.venv`、`node_modules`、日志和缓存，`.gitignore` 已配置。
更新代码后按需重新安装依赖；不要重新复制配置文件，不要用共享快照覆盖个人数据库。
Git 不会自动同步各自后续产生的历史。

上传到自己新建的空 GitHub 仓库（替换最后的地址）：

```powershell
git init
git add .
git status --short
git commit -m "Share DeepResearch P0 P1 and sanitized history"
git branch -M main
git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPO.git
git push -u origin main
```

本目录没有复制原项目的 `.git`，不会携带旧提交中的密钥。
shared-data 包含用户授权分享的历史正文，上传后仓库访问者能够阅读。

## 验证

```powershell
.\backend\.venv\Scripts\python.exe scripts/test_import_history.py
$env:PYTHONPATH = (Resolve-Path backend/src).Path
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests
npm.cmd --prefix frontend run build
```

## 来源

上游：https://github.com/datawhalechina/hello-agents ，代码起点为 `code/chapter14`。
保留上游仓库的 `UPSTREAM_LICENSE.txt` 和原代码中的署名/许可元数据；本次整理未重新指定许可证。
第三方依赖各自遵循其许可证。P0/P1 修改记录见 `P0_GUIDE.txt`、`P1_GUIDE.txt`。
