#!/usr/bin/env python3
"""
用户管理 CLI（模块化版）
uv run main.py --help
"""
import json
import click
from src.config import get_conn
from src.user_service import UserService
from src.points_service import add_points
from src.address_service import AddressService
from src.reward_service import TeamRewardService

# ---------- 所有 CLI 命令 ----------
@click.group()
def cli():
    pass

@cli.command("init-db")
def init_db():
    """初始化库表"""
    from src.config import CREATE_USERS, CREATE_REFS, CREATE_AUDIT, CREATE_POINTS_LOG, CREATE_ADDRESSES, CREATE_TEAM_REWARDS
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_USERS)
            cur.execute(CREATE_REFS)
            cur.execute(CREATE_AUDIT)
            cur.execute(CREATE_POINTS_LOG)
            cur.execute(CREATE_ADDRESSES)
            cur.execute(CREATE_TEAM_REWARDS)
    click.secho("✅ 用户管理库表已创建/已存在", fg="green")

# ---------- 用户相关命令 ----------
@cli.command()
@click.argument("mobile")
@click.argument("password")
@click.option("-n", "--name")
@click.option("-r", "--referrer")
def register(mobile, password, name, referrer):
    """注册"""
    try:
        uid = UserService.register(mobile, password, name, referrer)
        click.secho(f"✅ 注册成功 UID={uid}", fg="green")
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")

@cli.command()
@click.argument("mobile")
@click.argument("password")
def login(mobile, password):
    """登录"""
    try:
        info = UserService.login(mobile, password)
        click.secho(f"✅ 登录成功 {json.dumps(info, ensure_ascii=False)}", fg="green")
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")

@cli.command()
@click.argument("mobile")
@click.argument("referrer_mobile")
def referrer(mobile, referrer_mobile):
    """绑定/换绑推荐人"""
    try:
        UserService.bind_referrer(mobile, referrer_mobile)
        click.secho("✅ 绑定成功", fg="green")
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")


@cli.command()
@click.argument("mobile")
def upgrade(mobile):
    """升 1 星（不可逆）"""
    try:
        new_lv = UserService.upgrade_one_star(mobile)
        click.secho(f"✅ 升级成功，当前 {new_lv} 星", fg="green")
    except ValueError as e:
        click.secho(f"❌ {e}", fg="red")

@cli.command("set-level")          # 注意用引号，因为含连字符
@click.argument("mobile")
@click.argument("new_level", type=click.IntRange(0, 6))
@click.option("--reason", default="后台手动调整")
def set_level(mobile, new_level, reason):
    """后台手动调星 0-6 星并审计"""
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
    """分页列表 + ID/星级区间筛选"""
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
    """查询用户详情 + 直推推荐人"""
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

@cli.command("refer-direct")
@click.argument("mobile")
@click.option("--page", default=1, help="第几页")
@click.option("--size", default=10, help="每页条数")
def refer_direct(mobile, page, size):
    """查看直推列表（一级）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. 先查总数（在 fetchall 之前）
            cur.execute("SELECT COUNT(*) AS c FROM user_referrals WHERE referrer_id=(SELECT id FROM users WHERE mobile=%s)", (mobile,))
            total = cur.fetchone()['c']

            # 2. 再查列表
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
            click.secho(f"----- 直推总数：{total}  -----", fg="cyan")

@cli.command("refer-team")
@click.argument("mobile")
@click.option("--max-layer", default=6, help="最大统计层级（1-6）")
def refer_team(mobile, max_layer):
    """统计团队人数（含下级直到指定层级），并输出每个成员的详细信息"""
    if max_layer < 1 or max_layer > 6:
        raise click.BadParameter("层级范围 1-6")
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. 先总数（在 fetchall 之前）
            cur.execute("""
                WITH RECURSIVE team AS (
                    SELECT id, 0 AS layer FROM users WHERE mobile=%s
                    UNION ALL
                    SELECT u.id, t.layer + 1
                    FROM user_referrals r
                    JOIN users u ON u.id = r.user_id
                    JOIN team t ON t.id = r.referrer_id
                    WHERE t.layer < %s
                )
                SELECT COUNT(*) AS cnt FROM team WHERE layer > 0
            """, (mobile, max_layer))
            total = cur.fetchone()['cnt']

            # 2. 再查列表
            cur.execute("""
                WITH RECURSIVE team AS (
                    SELECT id, mobile, name, member_level, 0 AS layer FROM users WHERE mobile=%s
                    UNION ALL
                    SELECT u.id, u.mobile, u.name, u.member_level, t.layer + 1
                    FROM user_referrals r
                    JOIN users u ON u.id = r.user_id
                    JOIN team t ON t.id = r.referrer_id
                    WHERE t.layer < %s
                )
                SELECT id, mobile, name, member_level, layer
                FROM team
                WHERE layer > 0
                ORDER BY layer, id
            """, (mobile, max_layer))
            rows = cur.fetchall()
            if not rows:
                click.secho("❌ 团队暂无数据", fg="yellow")
                return
            click.secho(f"=== 团队成员信息（≤{max_layer} 层） ===", fg="cyan")
            for r in rows:
                click.echo(f"ID: {r['id']}")
                click.echo(f"手机号: {r['mobile']}")
                click.echo(f"昵称: {r['name'] or '-'}")
                click.echo(f"当前星级: {r['member_level']} 星")
                click.echo(f"层级: {r['layer']}")
                click.echo("-" * 40)
            click.secho(f"团队总人数（≤{max_layer} 层）：{total}", fg="green")

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


@cli.command("refer-star")
@click.argument("mobile")
@click.option("--max-layer", default=6, help="最大统计层级（1-6）")
def refer_star(mobile, max_layer):
    """统计团队各星级人数，并输出每个星级的成员详细信息"""
    if max_layer < 1 or max_layer > 6:
        raise click.BadParameter("层级范围 1-6")
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. 先总数（在 fetchall 之前）
            cur.execute("""
                WITH RECURSIVE team AS (
                    SELECT id, member_level, 0 AS layer FROM users WHERE mobile=%s
                    UNION ALL
                    SELECT u.id, u.member_level, t.layer + 1
                    FROM user_referrals r
                    JOIN users u ON u.id = r.user_id
                    JOIN team t ON t.id = r.referrer_id
                    WHERE t.layer < %s
                )
                SELECT COUNT(*) AS cnt FROM team WHERE layer > 0
            """, (mobile, max_layer))
            total = cur.fetchone()['cnt']

            # 2. 再查列表
            cur.execute("""
                WITH RECURSIVE team AS (
                    SELECT id, mobile, name, member_level, 0 AS layer FROM users WHERE mobile=%s
                    UNION ALL
                    SELECT u.id, u.mobile, u.name, u.member_level, t.layer + 1
                    FROM user_referrals r
                    JOIN users u ON u.id = r.user_id
                    JOIN team t ON t.id = r.referrer_id
                    WHERE t.layer < %s
                )
                SELECT member_level, id, mobile, name
                FROM team
                WHERE layer > 0
                ORDER BY member_level, id
            """, (mobile, max_layer))
            rows = cur.fetchall()
            if not rows:
                click.secho("❌ 团队暂无数据", fg="yellow")
                return
            click.secho(f"=== 团队成员信息（≤{max_layer} 层） ===", fg="cyan")
            star_info = {}
            for r in rows:
                star = r['member_level']
                if star not in star_info:
                    star_info[star] = []
                star_info[star].append(r)
            for star, members in star_info.items():
                click.secho(f"=== {star} 星成员 ===", fg="green")
                for member in members:
                    click.echo(f"ID: {member['id']}")
                    click.echo(f"手机号: {member['mobile']}")
                    click.echo(f"昵称: {member['name'] or '-'}")
                    click.echo(f"当前星级: {star} 星")
                    click.echo("-" * 40)
            click.secho(f"团队总人数（≤{max_layer} 层）：{total}", fg="green")


@cli.command("audit-list")
@click.option("--mobile", help="被操作人手机号")
@click.option("--page", default=1, help="第几页")
@click.option("--size", default=10, help="每页条数")
def audit_list(mobile, page, size):
    """查看等级变动审计日志"""
    where, args = "", []
    if mobile:
        where = "WHERE u.mobile=%s"
        args.append(mobile)

    # 1. 先查总数（在 fetchall 之前）
    count_sql = f"SELECT COUNT(*) AS c FROM audit_log a JOIN users u ON u.id=a.user_id {where}"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, args)
            total = cur.fetchone()['c']

            # 2. 再查列表
            sql = f"""
                SELECT u.mobile, a.old_val, a.new_val, a.reason, a.created_at
                FROM audit_log a
                JOIN users u ON u.id=a.user_id
                {where}
                ORDER BY a.created_at DESC
                LIMIT %s OFFSET %s
            """
            args.extend([size, (page - 1) * size])
            cur.execute(sql, args)
            rows = cur.fetchall()
            if not rows:
                click.secho("❌ 无审计记录", fg="yellow")
                return
            for r in rows:
                click.echo(f"{r['created_at']}  {r['mobile']}  {r['old_val']}→{r['new_val']}  原因：{r['reason']}")
            click.secho(f"----- 第 {page} 页 / 共 {total} 条 -----", fg="cyan")

@cli.command("address-add")
@click.argument("mobile")
@click.argument("name")
@click.argument("phone")
@click.argument("province")
@click.argument("city")
@click.argument("district")
@click.argument("detail")
@click.option("--default", is_flag=True, help="设为默认地址")
@click.option("--type", "addr_type", type=click.Choice(["shipping", "return"], case_sensitive=False), default="shipping", help="地址类型")
def address_add(mobile, name, phone, province, city, district, detail, default, addr_type):
    """新增收货地址（可设默认）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise click.BadParameter("用户不存在")
            addr_id = AddressService.add_address(
                u["id"], name, phone, province, city, district, detail, default, addr_type
            )
            click.secho(f"✅ 地址已添加 ID={addr_id}", fg="green")



@cli.command("points-balance")
@click.argument("mobile")
def points_balance(mobile):
    """查当前积分余额（同时输出用户积分、商家积分和可提取余额）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT member_points, merchant_points, withdrawable_balance FROM users WHERE mobile=%s",
                (mobile,)
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("用户不存在")
            click.secho(f"当前用户积分余额：{row['member_points']}", fg="green")
            click.secho(f"当前商家积分余额：{row['merchant_points']}", fg="green")
            click.secho(f"当前可提取余额：{row['withdrawable_balance']}", fg="green")

# ---------- 地址相关命令 ----------
@cli.command("address-list")
@click.argument("mobile")
@click.option("--page", type=int, default=1, help="页码，默认为 1")
@click.option("--size", type=int, default=5, help="每页显示的数量，默认为 5")
def address_list(mobile, page, size):
    """查询用户地址列表"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. 先查总数（在 fetchall 之前）
            cur.execute("SELECT COUNT(*) AS total FROM addresses WHERE user_id=(SELECT id FROM users WHERE mobile=%s)", (mobile,))
            total = cur.fetchone()['total']

            # 2. 再查列表
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            user = cur.fetchone()
            if not user:
                raise click.BadParameter("用户不存在")
            user_id = user["id"]
            addresses = AddressService.get_address_list(user_id, page, size)
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
            click.secho(f"----- 第 {page} 页 / 共 {total} 条 -----", fg="cyan")

@cli.command("return-addr-set")
@click.argument("mobile")
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
            addr_id = AddressService.add_address(
                u["id"], name, phone, province, city, district, detail, is_default=True, addr_type="return"
            )
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
            addr = AddressService.get_default_address(u["id"])
            if not addr:
                click.secho("❌ 未设置退货地址", fg="yellow")
                return
            click.echo(f"收件人：{addr['name']}  手机：{addr['phone']}")
            click.echo(f"地址：{addr['province']} {addr['city']} {addr['district']} {addr['detail']}")
            click.echo(f"设置时间：{addr['created_at']}")

@cli.command("points-log")
@click.argument("mobile")
@click.option("--order", "order_no", help="关联订单号（可选）")
@click.option("--page", default=1, help="第几页")
@click.option("--size", default=10, help="每页条数")
@click.option("--type", "points_type", type=click.Choice(["member", "merchant"], case_sensitive=False), default="member", help="积分类型")
def points_log(mobile, order_no, page, size, points_type):
    """查看积分流水（可按积分类型筛选）"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                raise ValueError("用户不存在")
            where, args = ["user_id=%s", "points_type=%s"], [u["id"], points_type]
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
                click.secho(f"❌ 暂无 {points_type} 积分流水", fg="yellow")
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
            click.secho(f"----- {points_type} 积分 第 {page} 页 / 共 {total} 条 -----", fg="cyan")


# ---------- 团队奖励相关命令 ----------
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
            total = cur.fetchone()['c']
            click.secho(f"----- 第 {page} 页 / 共 {total} 条 -----", fg="cyan")

# ---------- 主入口 ----------
if __name__ == "__main__":
    cli()