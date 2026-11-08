# 教务管理系统

基于 Flask + MySQL 的高校教务管理系统，覆盖学生、教师、教务管理员三类角色，串起从教学计划、开课排课、选课、成绩与考试、教学评价，到学籍异动、重修、学分替代等审批事务的完整教学业务流程。

## 功能

| 角色 | 页面 | 主要功能 |
|---|---|---|
| 学生 | 24 个 | 查看课表与成绩、自主选课与退课、提交各类申请、参与评教、确认创新学分与专业分流 |
| 教师 | 7 个 | 维护教学班成绩比例、录入与导入成绩、查看授课课表与学生名单、查看学生评教 |
| 教务管理员 | 20 个 | 维护组织架构与人员、课程与开课、排课与考务、审核各类申请、发布公告、审计日志 |

后端接口按角色拆分：学生端 31 个、教师端 12 个、管理端 44 个。

## 技术栈

- **后端**：Python 3.9+，Flask 3.1，蓝图（Blueprint）分模块组织
- **数据库**：MySQL 8.0，InnoDB 引擎，utf8mb4 字符集，28 张表
- **前端**：原生 HTML / CSS / JavaScript，按角色分目录，通过 Fetch 调用后端接口，无框架依赖
- **部署**：gunicorn + WSGI，多进程

## 目录结构

```
app.py                入口：创建应用、注册蓝图、页面路由、错误处理
core.py               基础设施：连接池、装饰器、通用函数、课表导出
config.py             配置（自动加载 .env）
auth.py               认证与头像
common.py             公共数据（元数据、公告、作息）
student.py            学生端接口
teacher.py            教师端接口
admin.py              管理端接口
enrollment_sync.py    选课数据同步
wsgi.py               WSGI 入口
gunicorn.conf.py      生产服务器配置
init_db.py            首次初始化（建库建表 + 演示数据）
upgrade_db.py         升级补表（幂等，不清数据）
schema.sql            28 张表结构
templates/            52 个页面模板
static/               CSS / JS / 图片
explain_file/         需求、设计、接口、部署等文档
```

## 快速开始

```bash
# 1. 建虚拟环境并安装依赖
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt -r requirements-prod.txt

# 2. 配置数据库连接
cp .env.example .env
# 编辑 .env，至少修改 MYSQL_PASSWORD 和 SECRET_KEY

# 3. 初始化数据库（仅首次执行，会清空并重建所有表）
python init_db.py --yes

# 4. 启动
python app.py                     # 开发
gunicorn -c gunicorn.conf.py wsgi:app    # 生产
```

默认访问 `http://127.0.0.1:5000`。

## 演示账号

| 角色 | 账号 | 密码 |
|---|---|---|
| 管理员 | `admin` | `admin123` |
| 学生 | `2024001` | `123456` |
| 教师 | `T001` | `123456` |

**正式使用前务必修改**，尤其是管理员账号。

## 文档

`explain_file/` 下包含 9 份文档：

- `项目说明.md` — 最短部署路径与注意事项
- `部署文档.md` — 完整部署流程
- `需求开发文档.md` — 需求分析与功能划分
- `数据库设计文档.md` — E-R 图、关系模式、范式分析
- `接口文档.md` — 后端接口清单
- `教务系统结构与功能.md` — 模块与页面说明
- `变更记录.md` — 版本演进
- `隐私政策.md`、`第三方开源许可.md`

## 安全说明

- `.env`（数据库密码）与 `.secret_key`（会话签名密钥）**未纳入版本管理**，参见 `.gitignore`
- 首次启动会自动生成 `.secret_key` 并持久化，请勿提交或随包分发
- 部署在 Nginx 等反向代理之后时，需设置 `TRUST_PROXY=1`，否则登录限流会把所有用户识别为同一个 IP
- 系统已上线后更新代码请用 `python upgrade_db.py`，**不要**重跑 `init_db.py`

## License

见 [LICENSE](LICENSE)。
