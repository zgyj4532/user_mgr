#!/usr/bin/env python3
"""
用户管理 CLI（单文件版）
uv run user_mgr_v1.py --help
"""
import os
import json
import uuid
import datetime as dt
from typing import Optional

import pymysql
import bcrypt
import dotenv
import click

# ---------- 配置 ----------
dotenv.load_dotenv()
CFG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "rootpass"),
    "db": os.getenv("MYSQL_DATABASE", "userdb"),
    "charset": "utf8mb4",
    "autocommit": True,
}

# ---------- SQL ----------
CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    mobile VARCHAR(30) NOT NULL UNIQUE,
    password_hash CHAR(60) NOT NULL,
    name VARCHAR(100),
    member_level TINYINT NOT NULL DEFAULT 0,
    is_member TINYINT(1) NOT NULL DEFAULT 0,
    referral_id BIGINT UNSIGNED,
    points BIGINT NOT NULL DEFAULT 0,
    avatar_path VARCHAR(255),
    status TINYINT NOT NULL DEFAULT 0,
    level_changed_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_mobile (mobile),
    INDEX idx_member_level (member_level)
);
"""

CREATE_REFS = """
CREATE TABLE IF NOT EXISTS user_referrals (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    referrer_id BIGINT UNSIGNED,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user (user_id),
    INDEX idx_referrer (referrer_id)
);
"""

CREATE_AUDIT = """
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    op_type VARCHAR(30) NOT NULL,
    old_val INT,
    new_val INT,
    reason VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_dt (user_id, created_at)
);
"""

CREATE_POINTS_LOG = """
CREATE TABLE IF NOT EXISTS points_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    change_amount BIGINT NOT NULL,
    reason VARCHAR(255),
    related_order BIGINT UNSIGNED,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_dt (user_id, created_at)
);
"""

CREATE_ADDRESSES = """
CREATE TABLE IF NOT EXISTS addresses (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    province VARCHAR(50) NOT NULL,
    city VARCHAR(50) NOT NULL,
    district VARCHAR(50) NOT NULL,
    detail VARCHAR(255) NOT NULL,
    is_default TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    CONSTRAINT fk_addr_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_TEAM_REWARDS = """
CREATE TABLE IF NOT EXISTS team_rewards (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    from_user_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED,
    layer INT NOT NULL,
    reward_amount DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_dt (user_id, created_at),
    INDEX idx_order_id (order_id)
);
"""

CREATE_RETURN_ADDR = """
ALTER TABLE addresses
ADD COLUMN addr_type ENUM('shipping','return') NOT NULL DEFAULT 'shipping'
AFTER is_default,
DROP INDEX uk_return_addr,
ADD UNIQUE KEY uk_return_addr (user_id, addr_type);
"""

CREATE_POINTS_TYPE = """
ALTER TABLE points_log
ADD COLUMN type ENUM('member','merchant') NOT NULL DEFAULT 'member'
AFTER change_amount;
"""



# ---------- 工具 ----------
def get_conn():
    return pymysql.connect(**CFG, cursorclass=pymysql.cursors.DictCursor)

def hash_pwd(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()

def verify_pwd(pwd: str, hashed: str) -> bool:
    return bcrypt.checkpw(pwd.encode(), hashed.encode())

# ================= 用户核心 Service =================
class UserService:
    @staticmethod
    def register(mobile: str, pwd: str, name: Optional[str] = None, referrer_mobile: Optional[str] = None) -> int:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
                if cur.fetchone():
                    raise ValueError("手机号已注册")
                pwd_hash = hash_pwd(pwd)
                cur.execute("INSERT INTO users(mobile, password_hash, name) VALUES (%s,%s,%s)",
                            (mobile, pwd_hash, name))
                uid = cur.lastrowid
                if referrer_mobile:
                    cur.execute("SELECT id FROM users WHERE mobile=%s", (referrer_mobile,))
                    ref = cur.fetchone()
                    if ref:
                        cur.execute("INSERT INTO user_referrals(user_id, referrer_id) VALUES (%s,%s)",
                                    (uid, ref["id"]))
                return uid

    @staticmethod
    def login(mobile: str, pwd: str) -> dict:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, password_hash, member_level, is_member FROM users WHERE mobile=%s", (mobile,))
                row = cur.fetchone()
                if not row or not verify_pwd(pwd, row["password_hash"]):
                    raise ValueError("手机号或密码错误")
                token = str(uuid.uuid4())
                return {"uid": row["id"], "level": row["member_level"], "is_member": row["is_member"], "token": token}

    @staticmethod
    def upgrade_one_star(mobile: str) -> int:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, member_level FROM users WHERE mobile=%s", (mobile,))
                row = cur.fetchone()
                if not row:
                    raise ValueError("用户不存在")
                current = row["member_level"]
                if current >= 6:
                    raise ValueError("已是最高星级（6星）")
                new_level = current + 1
                cur.execute("UPDATE users SET member_level=%s, level_changed_at=NOW() WHERE mobile=%s",
                            (new_level, mobile))
                return new_level

    @staticmethod
    def bind_referrer(mobile: str, referrer_mobile: str):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
                u = cur.fetchone()
                if not u:
                    raise ValueError("被推荐人不存在")
                cur.execute("SELECT id FROM users WHERE mobile=%s", (referrer_mobile,))
                ref = cur.fetchone()
                if not ref:
                    raise ValueError("推荐人不存在")
                cur.execute(
                    "INSERT INTO user_referrals(user_id, referrer_id) VALUES (%s,%s) ON DUPLICATE KEY UPDATE referrer_id=%s",
                    (u["id"], ref["id"], ref["id"])
                )

    @staticmethod
    def set_level(mobile: str, new_level: int, reason: str = "后台手动调整"):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, member_level, name FROM users WHERE mobile=%s", (mobile,))
                row = cur.fetchone()
                if not row:
                    raise ValueError("用户不存在")
                old_level = row["member_level"]
                if old_level == new_level:
                    return old_level
                cur.execute(
                    "INSERT INTO audit_log(user_id, op_type, old_val, new_val, reason) VALUES (%s,'SET_LEVEL',%s,%s,%s)",
                    (row["id"], old_level, new_level, reason)
                )
                cur.execute("UPDATE users SET member_level=%s, level_changed_at=NOW() WHERE mobile=%s",
                            (new_level, mobile))
                return new_level

    @staticmethod
    def add_points_by_order(user_id: int, amount: int, order_id: int, reason: str = "购买商品"):
        """订单成交后自动加积分并记流水"""
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET points=points+%s WHERE id=%s", (amount, user_id))
                cur.execute(
                    "INSERT INTO points_log(user_id, change_amount, reason, related_order) VALUES (%s,%s,%s,%s)",
                    (user_id, amount, reason, order_id)
                )

# ================= 地址 Service =================
class AddressService:
    @staticmethod
    def add_address(user_id: int, name: str, phone: str, province: str, city: str, district: str, detail: str,
                    is_default: bool = False):
        with get_conn() as conn:
            with conn.cursor() as cur:
                if is_default:
                    cur.execute("UPDATE addresses SET is_default=0 WHERE user_id=%s", (user_id,))
                cur.execute("""
                    INSERT INTO addresses(user_id, name, phone, province, city, district, detail, is_default, addr_type)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (user_id, name, phone, province, city, district, detail, int(is_default), 'shipping'))
                return cur.lastrowid

    @staticmethod
    def delete_address(user_id: int, addr_id: int):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM addresses WHERE id=%s AND user_id=%s", (addr_id, user_id))
                if cur.rowcount == 0:
                    raise ValueError("地址不存在或无权删除")

    @staticmethod
    def update_address(user_id: int, addr_id: int, **kwargs):
        if not kwargs:
            raise ValueError("无更新内容")
        set_clause = ", ".join([f"{k}=%s" for k in kwargs])
        values = list(kwargs.values()) + [addr_id, user_id]
        with get_conn() as conn:
            with conn.cursor() as cur:
                if kwargs.get("is_default"):
                    cur.execute("UPDATE addresses SET is_default=0 WHERE user_id=%s", (user_id,))
                cur.execute(f"UPDATE addresses SET {set_clause} WHERE id=%s AND user_id=%s", values)
                if cur.rowcount == 0:
                    raise ValueError("地址不存在或无权修改")

    @staticmethod
    def get_address_list(user_id: int, page: int = 1, size: int = 10):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, phone, province, city, district, detail, is_default, created_at
                    FROM addresses
                    WHERE user_id=%s
                    ORDER BY is_default DESC, id DESC
                    LIMIT %s OFFSET %s
                """, (user_id, size, (page - 1) * size))
                return cur.fetchall()

    @staticmethod
    def get_default_address(user_id: int):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, phone, province, city, district, detail, created_at
                    FROM addresses
                    WHERE user_id=%s AND is_default=1
                    LIMIT 1
                """, (user_id,))
                return cur.fetchone()

# ================= CLI：用户管理 10 命令 =================
@click.group()
def cli():
    pass




@cli.command()
def init_db():
    """1. 初始化库表"""
    # ---------- 内部工具 ----------
    def _safe_alter(cur, sql, err_codes, name: str):
        """忽略指定 MySQL error code 列表"""
        try:
            cur.execute(sql)
        except pymysql.err.OperationalError as e:
            if e.args[0] in err_codes:
               pass
            else:
                raise
    # ---------- 正式逻辑 ----------
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_USERS)
            cur.execute(CREATE_REFS)
            cur.execute(CREATE_AUDIT)
            cur.execute(CREATE_POINTS_LOG)
            cur.execute(CREATE_ADDRESSES)
            cur.execute(CREATE_TEAM_REWARDS)
            _safe_alter(cur, CREATE_RETURN_ADDR, [1060, 1091], "退货地址索引/列")
            _safe_alter(cur, CREATE_POINTS_TYPE,  [1060],        "列 type")
    click.secho("✅ 用户管理库表已创建/已存在", fg="green")

@cli.command()
@click.argument("mobile")
@click.argument("password")
@click.option("-n", "--name")
@click.option("-r", "--referrer")
def register(mobile, password, name, referrer):
    """2. 注册"""
    try:
        uid = UserService.register(mobile, password, name, referrer)
        click.secho(f"✅ 注册成功 UID={uid}", fg="green")
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")

@cli.command()
@click.argument("mobile")
@click.argument("password")
def login(mobile, password):
    """3. 登录"""
    try:
        info = UserService.login(mobile, password)
        click.secho(f"✅ 登录成功 {json.dumps(info, ensure_ascii=False)}", fg="green")
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")

@cli.command()
@click.argument("mobile")
def upgrade(mobile):
    """4. 升 1 星（不可逆）"""
    try:
        new_lv = UserService.upgrade_one_star(mobile)
        click.secho(f"✅ 升级成功，当前 {new_lv} 星", fg="green")
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")

@cli.command()
@click.argument("mobile")
@click.argument("referrer_mobile")
def referrer(mobile, referrer_mobile):
    """5. 绑定推荐人"""
    try:
        UserService.bind_referrer(mobile, referrer_mobile)
        click.secho("✅ 绑定成功", fg="green")
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")

@cli.command("set-level")
@click.argument("mobile")
@click.argument("new_level", type=click.IntRange(0, 6))
@click.option("--reason", default="后台手动调整")
def set_level(mobile, new_level, reason):
    """6. 手动调星（0-6）并审计"""
    try:
        old = UserService.set_level(mobile, new_level, reason)
        if old == new_level:
            click.secho(f"当前已是 {new_level} 星，无需调整", fg="yellow")
        else:
            click.secho(f"✅ 等级调整完成：{mobile}  {old} 星 → {new_level} 星\n原因：{reason}", fg="green")
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")

@cli.command("user-list")
@click.option("--id-start", type=int, help="ID左区间（含）")
@click.option("--id-end", type=int, help="ID右区间（含）")
@click.option("--level-start", type=int, default=0, help="星级左区间（含）")
@click.option("--level-end", type=int, default=6, help="星级右区间（含）")
@click.option("--size", type=int, default=20, help="每页条数")
@click.option("--page", type=int, default=1, help="第几页，从1开始")
def user_list(id_start, id_end, level_start, level_end, size, page):
    """7. 分页列表 + ID/星级区间筛选"""
    if level_start > level_end or (id_start is not None and id_end is not None and id_start > id_end):
        raise click.BadParameter("区间左值不能大于右值")
    where, args = [], []
    if id_start is not None:
        where.append("id >= %s")
        args.append(id_start)
    if id_end is not None:
        where.append("id <= %s")
        args.append(id_end)
    where.append("member_level BETWEEN %s AND %s")
    args.extend([level_start, level_end])
    sql_where = "WHERE " + " AND ".join(where) if where else ""
    limit_sql = "LIMIT %s OFFSET %s"
    args.extend([size, (page - 1) * size])

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT id, mobile, name, member_level, created_at FROM users {sql_where} ORDER BY id {limit_sql}", args)
            rows = cur.fetchall()
            if not rows:
                click.secho("❌ 无数据", fg="yellow")
                return
            for r in rows:
                click.echo(f"ID={r['id']:>3}  mobile={r['mobile']}  level={r['member_level']}  name={r['name'] or '-'}  created_at={r['created_at']}")
            cur.execute(f"SELECT COUNT(*) AS c FROM users {sql_where}", args[:-2])
            total = cur.fetchone()['c']
            click.secho(f"----- 第 {page} 页 / 共 {total} 条 -----", fg="cyan")

@cli.command("user-info")
@click.argument("mobile")
def user_info(mobile):
    """8. 用户详情 + 直推推荐人"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, mobile, name, member_level, level_changed_at, created_at FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise ValueError("用户不存在")
            cur.execute("SELECT ru.mobile, ru.name, ru.member_level FROM user_referrals r JOIN users ru ON ru.id=r.referrer_id WHERE r.user_id=%s", (u["id"],))
            ref = cur.fetchone()
            click.secho("=== 用户详情 ===", fg="cyan")
            click.echo(f"ID           : {u['id']}")
            click.echo(f"手机号       : {u['mobile']}")
            click.echo(f"姓名         : {u['name'] or '-'}")
            click.echo(f"当前等级     : {u['member_level']} 星")
            click.echo(f"等级修改时间 : {u['level_changed_at'] or '从未调整'}")
            click.echo(f"注册时间     : {u['created_at']}")
            if ref:
                click.secho("=== 直推推荐人 ===", fg="green")
                click.echo(f"推荐人手机号 : {ref['mobile']}")
                click.echo(f"推荐人姓名   : {ref['name'] or '-'}")
                click.echo(f"推荐人等级   : {ref['member_level']} 星")
            else:
                click.secho("=== 直推推荐人 ===", fg="yellow")
                click.echo("暂无推荐人（或未绑定）")

@cli.command("audit-list")
@click.option("--mobile", help="被操作人手机号")
@click.option("--page", default=1, help="第几页")
@click.option("--size", default=10, help="每页条数")
def audit_list(mobile, page, size):
    """9. 等级变动审计日志"""
    where, args = "", []
    if mobile:
        where = "WHERE u.mobile=%s"
        args.append(mobile)
    sql = f"""
        SELECT u.mobile, a.old_val, a.new_val, a.reason, a.created_at
        FROM audit_log a
        JOIN users u ON u.id=a.user_id
        {where}
        ORDER BY a.created_at DESC
        LIMIT %s OFFSET %s
    """
    args.extend([size, (page - 1) * size])
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            rows = cur.fetchall()
            if not rows:
                click.secho("❌ 无审计记录", fg="yellow")
                return
            for r in rows:
                click.echo(f"{r['created_at']}  {r['mobile']}  {r['old_val']}→{r['new_val']}  原因：{r['reason']}")

@cli.command("clear-data")
@click.confirmation_option(prompt="确定清空所有业务数据？（不可回滚）")
def clear_data():
    """10. 一键清空 users / user_referrals / audit_log 数据"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            cur.execute("TRUNCATE TABLE audit_log")
            cur.execute("TRUNCATE TABLE user_referrals")
            cur.execute("TRUNCATE TABLE users")
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
    click.secho("✅ 全部业务数据已清空，自增 ID 归零", fg="green")

# ================= 积分只读接口 =================
@cli.command("points-balance")
@click.argument("mobile")
def points_balance(mobile):
    """查当前积分余额（同时输出用户积分、商家积分和可提取余额）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT member_points, merchant_points, withdrawable_balance FROM users WHERE mobile=%s", (mobile,))
            row = cur.fetchone()
            if not row:
                raise ValueError("用户不存在")
            click.secho(f"当前用户积分余额：{row['member_points']}", fg="green")
            click.secho(f"当前商家积分余额：{row['merchant_points']}", fg="green")
            click.secho(f"当前可提取余额：{row['withdrawable_balance']}", fg="green")

@cli.command("points-log")
@click.argument("mobile")
@click.option("--order", "order_no", help="关联订单号（可选）")
@click.option("--page", default=1, help="第几页")
@click.option("--size", default=10, help="每页条数")
def points_log(mobile, order_no, page, size):
    """查看积分流水（仅购买商品产生）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise ValueError("用户不存在")
            where, args = ["user_id=%s"], [u["id"]]
            if order_no:
                where.append("related_order=%s")
                args.append(order_no)
            sql_where = " AND ".join(where)
            sql = f"""
                SELECT change_amount, reason, related_order, created_at
                FROM points_log
                WHERE {sql_where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            args.extend([size, (page - 1) * size])
            cur.execute(sql, args)
            rows = cur.fetchall()
            if not rows:
                click.secho("❌ 无积分流水", fg="yellow")
                return
            for r in rows:
                click.echo(
                    f"{r['created_at']}  "
                    f"{r['change_amount']:>+8}  "
                    f"原因：{r['reason']}  "
                    f"订单：{r['related_order'] or '-'}"
                )
            cur.execute(f"SELECT COUNT(*) AS c FROM points_log WHERE {sql_where}", args[:-2])
            total = cur.fetchone()['c']
            click.secho(f"----- 第 {page} 页 / 共 {total} 条 -----", fg="cyan")

# ================= 推荐关系查询（只读） =================
@cli.command("refer-direct")
@click.argument("mobile")
@click.option("--page", default=1, help="第几页")
@click.option("--size", default=10, help="每页条数")
def refer_direct(mobile, page, size):
    """查看直推列表（一级）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise ValueError("用户不存在")
            cur.execute("""
                SELECT u.id, u.mobile, u.name, u.member_level, u.created_at
                FROM user_referrals r
                JOIN users u ON u.id = r.user_id
                WHERE r.referrer_id=%s
                ORDER BY u.created_at DESC
                LIMIT %s OFFSET %s
            """, (u["id"], size, (page - 1) * size))
            rows = cur.fetchall()
            if not rows:
                click.secho("❌ 暂无直推用户", fg="yellow")
                return
            for r in rows:
                click.echo(f"ID={r['id']:>3}  mobile={r['mobile']}  level={r['member_level']}  name={r['name'] or '-'}  注册时间={r['created_at']}")
            cur.execute("SELECT COUNT(*) AS c FROM user_referrals WHERE referrer_id=%s", (u["id"],))
            total = cur.fetchone()['c']
            click.secho(f"----- 直推总数：{total}  -----", fg="cyan")

@cli.command("refer-team")
@click.argument("mobile")
@click.option("--max-layer", default=6, help="最大统计层级（1-6）")
def refer_team(mobile, max_layer):
    """统计团队人数（含下级直到指定层级）"""
    if max_layer < 1 or max_layer > 6:
        raise click.BadParameter("层级范围 1-6")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise ValueError("用户不存在")
            cur.execute("""
                WITH RECURSIVE team AS (
                    SELECT id, 0 AS layer FROM users WHERE id=%s
                    UNION ALL
                    SELECT u.id, t.layer + 1
                    FROM user_referrals r
                    JOIN users u ON u.id = r.user_id
                    JOIN team t ON t.id = r.referrer_id
                    WHERE t.layer < %s
                )
                SELECT COUNT(*) AS cnt FROM team WHERE layer > 0
            """, (u["id"], max_layer))
            total = cur.fetchone()['cnt']
            click.secho(f"团队总人数（≤{max_layer} 层）：{total}", fg="green")

@cli.command("refer-star")
@click.argument("mobile")
@click.option("--max-layer", default=6, help="最大统计层级（1-6）")
def refer_star(mobile, max_layer):
    """统计团队各星级人数"""
    if max_layer < 1 or max_layer > 6:
        raise click.BadParameter("层级范围 1-6")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise ValueError("用户不存在")
            cur.execute("""
                WITH RECURSIVE team AS (
                    SELECT id, member_level, 0 AS layer FROM users WHERE id=%s
                    UNION ALL
                    SELECT u.id, u.member_level, t.layer + 1
                    FROM user_referrals r
                    JOIN users u ON u.id = r.user_id
                    JOIN team t ON t.id = r.referrer_id
                    WHERE t.layer < %s
                )
                SELECT member_level, COUNT(*) AS cnt
                FROM team
                WHERE layer > 0
                GROUP BY member_level
                ORDER BY member_level
            """, (u["id"], max_layer))
            rows = cur.fetchall()
            if not rows:
                click.secho("❌ 团队暂无数据", fg="yellow")
                return
            click.secho("=== 团队星级分布 ===", fg="cyan")
            for r in rows:
                click.echo(f"{r['member_level']} 星：{r['cnt']} 人")

# ================= CLI：删除唯一键索引 =================
@cli.command("drop-return-addr-index")
def drop_return_addr_index():
    """删除 addresses 表的 uk_return_addr 索引"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("ALTER TABLE addresses DROP INDEX uk_return_addr")
                click.secho("✅ 已删除 uk_return_addr 索引", fg="green")
            except pymysql.err.OperationalError as e:
                click.secho(f"⚠ 索引 uk_return_addr 不存在或已删除：{e}", fg="yellow")


# ================= 地址 CLI：地址列表 =================
@cli.command("address-list")
@click.argument("mobile")
@click.option("--page", type=int, default=1, help="页码，默认为 1")
@click.option("--size", type=int, default=5, help="每页显示的数量，默认为 5")
def address_list(mobile, page, size):
    """查询用户地址列表"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            user = cur.fetchone()
            if not user:
                raise click.BadParameter("用户不存在")
            user_id = user["id"]

            # 查询地址列表
            offset = (page - 1) * size
            cur.execute("""
                SELECT id, name, phone, province, city, district, detail, is_default, created_at
                FROM addresses
                WHERE user_id=%s
                ORDER BY is_default DESC, created_at DESC
                LIMIT %s OFFSET %s
            """, (user_id, size, offset))
            addresses = cur.fetchall()

            if not addresses:
                click.secho("暂无地址信息", fg="yellow")
                return

            for addr in addresses:
                click.echo(f"ID: {addr['id']}")
                click.echo(f"收件人: {addr['name']}")
                click.echo(f"手机号: {addr['phone']}")
                click.echo(f"地址: {addr['province']} {addr['city']} {addr['district']} {addr['detail']}")
                click.echo(f"是否默认: {'是' if addr['is_default'] else '否'}")
                click.echo(f"创建时间: {addr['created_at']}")
                click.echo("-" * 40)

            # 查询总记录数
            cur.execute("SELECT COUNT(*) AS total FROM addresses WHERE user_id=%s", (user_id,))
            total = cur.fetchone()["total"]
            click.secho(f"----- 第 {page} 页 / 共 {total} 条 -----", fg="cyan")


# ================= 团队奖励记录（只读） =================
class TeamRewardService:
    @staticmethod
    def add_reward(user_id: int, from_user_id: int, layer: int, amount: float, order_id: Optional[int] = None):
        """订单模块调用：写入团队奖励记录"""
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO team_rewards(user_id, from_user_id, order_id, layer, reward_amount)
                    VALUES (%s,%s,%s,%s,%s)
                """, (user_id, from_user_id, order_id, layer, amount))

    @staticmethod
    def get_reward_list_by_user(user_id: int, page: int = 1, size: int = 10):
        """按获奖用户分页查奖励"""
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tr.id, tr.from_user_id, tr.order_id, tr.layer, tr.reward_amount, tr.created_at,
                           u.mobile AS from_mobile, u.name AS from_name
                    FROM team_rewards tr
                    JOIN users u ON u.id = tr.from_user_id
                    WHERE tr.user_id=%s
                    ORDER BY tr.created_at DESC
                    LIMIT %s OFFSET %s
                """, (user_id, size, (page - 1) * size))
                return cur.fetchall()

    @staticmethod
    def get_reward_by_order(order_id: int):
        """按订单查全部团队奖励明细"""
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tr.id, tr.user_id, tr.from_user_id, tr.layer, tr.reward_amount, tr.created_at,
                           u.mobile AS user_mobile, u.name AS user_name,
                           fu.mobile AS from_mobile, fu.name AS from_name
                    FROM team_rewards tr
                    JOIN users u ON u.id = tr.user_id
                    JOIN users fu ON fu.id = tr.from_user_id
                    WHERE tr.order_id=%s
                    ORDER BY tr.layer, tr.id
                """, (order_id,))
                return cur.fetchall()


# ================= 团队奖励 CLI（只读） =================
@cli.command("reward-list")
@click.argument("mobile")
@click.option("--page", default=1, help="第几页")
@click.option("--size", default=10, help="每页条数")
def reward_list(mobile, page, size):
    """查看团队奖励列表（获奖人视角）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise ValueError("用户不存在")
            rows = TeamRewardService.get_reward_list_by_user(u["id"], page, size)
            if not rows:
                click.secho("❌ 暂无团队奖励", fg="yellow")
                return
            for r in rows:
                click.echo(
                    f"{r['created_at']}  "
                    f"层={r['layer']}  "
                    f"奖励={r['reward_amount']:>8.2f}  "
                    f"来源={r['from_name'] or '-'}({r['from_mobile']})  "
                    f"订单={r['order_id'] or '-'}"
                )
            cur.execute("SELECT COUNT(*) AS c FROM team_rewards WHERE user_id=%s", (u["id"],))
            total = cur.fetchone()['c']
            click.secho(f"----- 第 {page} 页 / 共 {total} 条 -----", fg="cyan")

@cli.command("reward-by-order")
@click.argument("order_id")
def reward_by_order(order_id):
    """按订单查看团队奖励明细"""
    rows = TeamRewardService.get_reward_by_order(order_id)
    if not rows:
        click.secho("❌ 该订单无团队奖励", fg="yellow")
        return
    click.secho(f"=== 订单 {order_id} 团队奖励明细 ===", fg="cyan")
    for r in rows:
        click.echo(
            f"层={r['layer']}  "
            f"获奖人={r['user_name'] or '-'}({r['user_mobile']})  "
            f"来源={r['from_name'] or '-'}({r['from_mobile']})  "
            f"金额={r['reward_amount']:>8.2f}  "
            f"时间={r['created_at']}"
        )


# ================= 头像路径管理 =================
@cli.command("avatar-set")
@click.argument("mobile")
@click.argument("path")
def avatar_set(mobile, path):
    """更新用户头像相对路径（前端上传后调用）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET avatar_path=%s WHERE mobile=%s", (path, mobile))
            if cur.rowcount == 0:
                raise ValueError("用户不存在")
        click.secho(f"✅ 头像路径已更新：{path}", fg="green")

@cli.command("avatar-get")
@click.argument("mobile")
def avatar_get(mobile):
    """获取用户头像相对路径"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT avatar_path FROM users WHERE mobile=%s", (mobile,))
            row = cur.fetchone()
            if not row:
                raise ValueError("用户不存在")
            path = row["avatar_path"]
            click.echo(path if path else "未设置头像")

# ================= 地址 CLI：新增地址 =================
@cli.command("address-add")
@click.argument("mobile")
@click.argument("name")
@click.argument("phone")
@click.argument("province")
@click.argument("city")
@click.argument("district")
@click.argument("detail")
@click.option("--default", is_flag=True, help="设为默认地址")
def address_add(mobile, name, phone, province, city, district, detail, default):
    """新增收货地址（可设默认）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise click.BadParameter("用户不存在")
            addr_id = AddressService.add_address(
                u["id"], name, phone, province, city, district, detail, default
            )
            click.secho(f"✅ 地址已添加 ID={addr_id}", fg="green")





# ================= 商家退货地址（type='return'） =================
class ReturnAddrService:
    @staticmethod
    def set_return_address(user_id: int, name: str, phone: str, province: str, city: str, district: str, detail: str):
        """商家设置/更新退货地址（每个商家仅一条）"""
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO addresses(user_id, name, phone, province, city, district, detail, is_default, type)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,1,'return')
                    ON DUPLICATE KEY UPDATE
                        name=VALUES(name), phone=VALUES(phone), province=VALUES(province),
                        city=VALUES(city), district=VALUES(district), detail=VALUES(detail),
                        updated_at=NOW()
                """, (user_id, name, phone, province, city, district, detail))
                return cur.lastrowid

    @staticmethod
    def get_return_address(user_id: int):
        """取商家当前退货地址"""
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, phone, province, city, district, detail, created_at
                    FROM addresses
                    WHERE user_id=%s AND type='return'
                    LIMIT 1
                """, (user_id,))
                return cur.fetchone()


# ========== 商家退货地址 CLI ==========
@cli.command("return-addr-set")
@click.argument("mobile")   # 商家手机号
@click.argument("name")
@click.argument("phone")
@click.argument("province")
@click.argument("city")
@click.argument("district")
@click.argument("detail")
def return_addr_set(mobile, name, phone, province, city, district, detail):
    """商家设置/更新退货地址（每个商家仅一条）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise ValueError("商家不存在")
            addr_id = ReturnAddrService.set_return_address(u["id"], name, phone, province, city, district, detail)
            click.secho(f"✅ 退货地址已设置/更新 ID={addr_id}", fg="green")

@cli.command("return-addr-get")
@click.argument("mobile")
def return_addr_get(mobile):
    """查看商家当前退货地址"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise ValueError("商家不存在")
            addr = ReturnAddrService.get_return_address(u["id"])
            if not addr:
                click.secho("❌ 未设置退货地址", fg="yellow")
                return
            click.echo(f"收件人：{addr['name']}  手机：{addr['phone']}")
            click.echo(f"地址：{addr['province']} {addr['city']} {addr['district']} {addr['detail']}")
            click.echo(f"设置时间：{addr['created_at']}")

# ================= 地址 CLI =================
@cli.command("address-add")
@click.argument("mobile")
@click.argument("name")
@click.argument("phone")
@click.argument("province")
@click.argument("city")
@click.argument("district")
@click.argument("detail")
@click.option("--default", is_flag=True, help="设为默认地址")
def address_add(mobile, name, phone, province, city, district, detail, default):
    """新增收货地址（可设默认）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise click.BadParameter("用户不存在")
            addr_id = AddressService.add_address(
                u["id"], name, phone, province, city, district, detail, default
            )
            click.secho(f"✅ 地址已添加 ID={addr_id}", fg="green")



# ================= 身份切换 & 双积分 =================
class IdentityService:
    @staticmethod
    def switch_mode(mobile: str, new_mode: str):
        """0=普通用户 1=商家"""
        if new_mode not in (0, 1):
            raise ValueError("mode 只能是 0（用户）或 1（商家）")
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET is_member=%s WHERE mobile=%s", (new_mode, mobile))
                if cur.rowcount == 0:
                    raise ValueError("用户不存在")

    @staticmethod
    def current_mode(mobile: str) -> int:
        """返回当前身份 0/1"""
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT is_member FROM users WHERE mobile=%s", (mobile,))
                row = cur.fetchone()
                if not row:
                    raise ValueError("用户不存在")
                return row["is_member"]

@cli.command("register")
@click.argument("mobile")
@click.argument("password")
@click.option("-n", "--name")
@click.option("-r", "--referrer")
@click.option("--merchant", is_flag=True, help="注册为商家（is_member=1）")
def register(mobile, password, name, referrer, merchant):
    """2. 注册（可一键选身份）"""
    try:
        uid = UserService.register(mobile, password, name, referrer)
        # 注册后立即设定身份
        IdentityService.switch_mode(mobile, 1 if merchant else 0)
        role = "商家" if merchant else "普通用户"
        click.secho(f"✅ 注册成功 UID={uid} 身份：{role}", fg="green")
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")

@cli.command("switch-mode")
@click.argument("mobile")
@click.argument("mode", type=click.Choice(["0", "1"], case_sensitive=False))
def switch_mode(mobile, mode):
    """0=普通用户 1=商家"""
    try:
        IdentityService.switch_mode(mobile, int(mode))
        role = "商家" if mode == "1" else "普通用户"
        click.secho(f"✅ 已切换为：{role}", fg="green")
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")

@cli.command("points-log")
@click.argument("mobile")
@click.option("--order", "order_no", help="关联订单号（可选）")
@click.option("--page", default=1, help="第几页")
@click.option("--size", default=10, help="每页条数")
@click.option("--mode", type=click.Choice(["member", "merchant"], case_sensitive=False), default="member", help="积分类型")
def points_log(mobile, order_no, page, size, mode):
    """查看积分流水（可按身份类型筛选）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise ValueError("用户不存在")
            where, args = ["user_id=%s", "type=%s"], [u["id"], mode]
            if order_no:
                where.append("related_order=%s")
                args.append(order_no)
            sql_where = " AND ".join(where)
            sql = f"""
                SELECT change_amount, reason, related_order, created_at
                FROM points_log
                WHERE {sql_where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            args.extend([size, (page - 1) * size])
            cur.execute(sql, args)
            rows = cur.fetchall()
            if not rows:
                click.secho(f"❌ 暂无 {mode} 积分流水", fg="yellow")
                return
            for r in rows:
                click.echo(
                    f"{r['created_at']}  "
                    f"{r['change_amount']:>+8}  "
                    f"原因：{r['reason']}  "
                    f"订单：{r['related_order'] or '-'}"
                )
            cur.execute(f"SELECT COUNT(*) AS c FROM points_log WHERE {sql_where}", args[:-2])
            total = cur.fetchone()['c']
            click.secho(f"----- {mode} 积分 第 {page} 页 / 共 {total} 条 -----", fg="cyan")

if __name__ == "__main__":
    cli()