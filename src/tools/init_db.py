#!/usr/bin/env python3
"""
一次性初始化数据库脚本
只在第一次部署 / 换新库时执行
用法：在项目根目录下
    python tools/init_db.py
在项目根目录安装依赖（如果还没装）
pip install pymysql python-dotenv
# 务必在 项目根目录 下运行
python tools/init_db.py
"""
import sys
import pathlib
import pymysql
from pymysql.err import Error

# 把项目根目录塞进 PYTHONPATH，否则无法 import src.*
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.config import CFG, CREATE_USERS, CREATE_REFS, CREATE_AUDIT, \
    CREATE_POINTS_LOG, CREATE_ADDRESSES, CREATE_TEAM_REWARDS, \
    CREATE_DIRECTORS, CREATE_DIRECTOR_DIVIDENDS

# 如果 six_director / six_team 已经加过，就把下面这一行注释掉
ALTER_USERS = """
ALTER TABLE users
  ADD COLUMN six_director TINYINT NOT NULL DEFAULT 0 COMMENT '直推六星人数',
  ADD COLUMN six_team     INT  NOT NULL DEFAULT 0 COMMENT '团队六星人数';
"""
# 与 CFG 使用同一库名
CREATE_DATABASE = f"CREATE DATABASE IF NOT EXISTS `{CFG['db']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"


DDL_LIST = [
    CREATE_USERS,
    CREATE_REFS,
    CREATE_AUDIT,
    CREATE_POINTS_LOG,
    CREATE_ADDRESSES,
    CREATE_TEAM_REWARDS,
    CREATE_DIRECTORS,
    CREATE_DIRECTOR_DIVIDENDS,
    ALTER_USERS,
]

def main() -> None:
    print("连接数据库 …")
    conn = pymysql.connect(**CFG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            for idx, sql in enumerate(DDL_LIST, 1):
                try:
                    print(f"[{idx}/{len(DDL_LIST)}] 正在执行 …")
                    cur.execute(sql)
                except Error as e:
                    # 1060 表示字段已存在，可以忽略
                    if e.args[0] == 1060:
                        print("   字段已存在，跳过")
                    else:
                        print("   ❌ 失败：", e)
                        raise
        conn.commit()
        print("---- 数据库初始化完毕 ✅ ----")
    finally:
        conn.close()

# tools/init_db.py 末尾新增
def init_database():
    """供 main.py 调用的自动化入口"""
    tmp_cfg = CFG.copy()
    tmp_cfg['db'] = 'mysql'          # 先连系统库
    conn = pymysql.connect(**tmp_cfg, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_DATABASE)
        conn.commit()
    finally:
        conn.close()

    # 再连目标库跑 DDL
    conn = pymysql.connect(**CFG, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            for sql in DDL_LIST:
                try:
                    cur.execute(sql)
                except pymysql.err.Error as e:
                    if e.args[0] == 1060:      # 字段已存在
                        continue
                    raise
        conn.commit()
    finally:
        conn.close()


if __name__ == '__main__':
    main()