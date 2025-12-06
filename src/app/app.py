import pymysql
from fastapi import FastAPI

from src.config import CFG
from src.tools.init_db import init_database
from src.app.routes import register_routes


def ensure_database():
    try:
        pymysql.connect(**CFG, cursorclass=pymysql.cursors.DictCursor).close()
    except pymysql.err.OperationalError as e:
        if e.args[0] == 1049:
            print("📦 数据库不存在，正在自动创建并初始化 …")
            init_database()
            print("✅ 自动初始化完成！")
        elif e.args[0] == 1045:
            # 引导用户填写 .env 数据库连接信息，仅输出提示不展示堆栈
            msg = (
                "未配置 .env 信息，请添加。文件示例： MYSQL_HOST=127.0.0.1 MYSQL_PORT=3306 "
                "MYSQL_USER=root MYSQL_PASSWORD=password MYSQL_DATABASE=finan_manage_db"
            )
            raise SystemExit(msg)
        else:
            raise


ensure_database()


app = FastAPI(title="用户中心", version="1.0.0")


register_routes(app)
