#!/usr/bin/env python3
# -------------  第 1 步：把项目根塞进 PATH --------------
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

# -------------  第 2 步：正常写 FastAPI 代码 --------------
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional


# ****** 第 3 步：所有 import 都显式带 src. ******
# -------------- 原来 import 保持不变 --------------
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi import Form, UploadFile, File
from typing import List, Optional
import pymysql
from src.config import CFG
from tools.init_db import init_database   # 现在可以安全导入
from src.config import (
    get_conn, CREATE_USERS, CREATE_REFS, CREATE_AUDIT,
    CREATE_POINTS_LOG, CREATE_ADDRESSES, CREATE_TEAM_REWARDS,
    CREATE_DIRECTORS, CREATE_DIRECTOR_DIVIDENDS
)
from src.user_service import UserService, UserStatus   # ★ 记得带 UserStatus
from src.address_service import AddressService
from src.points_service import add_points
from src.reward_service import TeamRewardService
from src.director_service import DirectorService
import datetime
import uuid  # 新增
from src.user_service import verify_pwd  # 新增
from src.user_service import UserService, UserStatus  # 已有
from src.user_service import hash_pwd
from src.wechat_service import wechat_login
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse


def ensure_database():
    try:
        # 尝试连目标库
        pymysql.connect(**CFG, cursorclass=pymysql.cursors.DictCursor).close()
    except pymysql.err.OperationalError as e:
        if e.args[0] == 1049:                # 库不存在
            print("📦 数据库不存在，正在自动创建并初始化 …")
            init_database()
            print("✅ 自动初始化完成！")
        else:
            raise                              # 其他错误继续抛

ensure_database()   # 这里立即执行，保证在 uvicorn 加载路由前完成



# -------------- 初始化 FastAPI --------------
app = FastAPI(title="用户中心", version="1.0.0")
# -------------- 新增：用户状态切换请求模型 --------------
class SetStatusReq(BaseModel):
    mobile: str
    new_status: UserStatus = Field(..., description="0-正常 1-冻结 2-注销")
    reason: str = "后台调整"


app = FastAPI()

@app.post('/user/wechat_login', summary="微信一键登录")
async def wechat_login_route(request: Request):
    try:
        # 调用微信登录逻辑
        response = await wechat_login(request)
        return JSONResponse(content=response, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)






# -------------- 新增：用户状态切换接口 --------------
@app.post("/user/set-status", summary="冻结/注销/恢复正常")
def set_user_status(body: SetStatusReq):
    try:
        ok = UserService.set_status(body.mobile, body.new_status, body.reason)
        return {"success": ok}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# -------------- 通用异常 --------------
def _err(msg: str):
    raise HTTPException(status_code=400, detail=msg)

# -------------- 数据模型 --------------
class RegisterReq(BaseModel):
    mobile: str
    password: str
    name: Optional[str] = None
    referrer_mobile: Optional[str] = None

class LoginReq(BaseModel):
    mobile: str
    password: str

class SetLevelReq(BaseModel):
    mobile: str
    new_level: int = Field(ge=0, le=6)
    reason: str = "后台手动调整"

class AddressReq(BaseModel):
    mobile: str
    name: str
    phone: str
    province: str
    city: str
    district: str
    detail: str
    is_default: bool = False
    addr_type: str = "shipping"

class PointsReq(BaseModel):
    mobile: str
    points_type: str = Field(pattern="^(member|merchant)$")
    amount: int
    reason: str = "系统赠送"

class PageQuery(BaseModel):
    page: int = Query(1, ge=1)
    size: int = Query(10, ge=1, le=200)

class AuthReq(BaseModel):
    mobile: str
    password: str
    name: Optional[str] = None   # 第一次可传昵称，后续忽略

class AuthResp(BaseModel):
    uid: int
    token: str
    level: int
    is_new: bool          # true=今天刚注册

# -------------- 新增：个人中心完整信息 --------------
class UserInfoResp(BaseModel):
    uid: int
    mobile: str
    name: Optional[str]
    avatar_path: Optional[str]
    member_level: int
    referral_code: Optional[str]
    direct_count: int
    team_total: int
    assets: dict
    referrer: Optional[dict] = None

# -------------- 修改资料 --------------
class UpdateProfileReq(BaseModel):
    mobile: str
    name: Optional[str] = None
    avatar_path: Optional[str] = None   # 先传图→得URL→再填这里
    old_password: Optional[str] = None  # 改密码时必须
    new_password: Optional[str] = None  # 改密码时必须

# -------------- 密码相关 --------------
class ResetPwdReq(BaseModel):
    mobile: str
    sms_code: str = Field(..., description="短信验证码（先 mock 111111）")
    new_password: str

class AdminResetPwdReq(BaseModel):
    mobile: str
    new_password: str
    admin_key: str = Field(..., description="后台口令")

# -------------- 状态管理 --------------
class SelfDeleteReq(BaseModel):
    mobile: str
    password: str                   # 验证本人
    reason: str = "用户自助注销"

class FreezeReq(BaseModel):
    mobile: str
    admin_key: str = Field(..., description="后台口令")
    reason: str = "后台冻结/解冻"

class ResetPasswordReq(BaseModel):
    mobile: str
    sms_code: str  # 短信验证码
    new_password: str  # 新密码

# -------------- 用户模块 --------------
@app.post("/user/auth", summary="一键登录（不存在则自动注册）")
def user_auth(body: AuthReq):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, password_hash, member_level, status FROM users WHERE mobile=%s", (body.mobile,))
            row = cur.fetchone()

            # 1. 已存在 → 直接登录
            if row:
                if not verify_pwd(body.password, row["password_hash"]):
                    raise HTTPException(status_code=400, detail="手机号或密码错误")
                status = row["status"]
                if status == UserStatus.FROZEN:
                    raise HTTPException(status_code=403, detail="账号已冻结")
                if status == UserStatus.DELETED:
                    raise HTTPException(status_code=403, detail="账号已注销")
                token = str(uuid.uuid4())
                return AuthResp(uid=row["id"], token=token, level=row["member_level"], is_new=False)

            # 2. 不存在 → 自动注册 + 登录
            try:
                uid = UserService.register(
                    mobile=body.mobile,
                    pwd=body.password,
                    name=body.name,
                    referrer_mobile=None   # 可扩展填推荐人
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            # 3. 返回 token
            token = str(uuid.uuid4())
            return AuthResp(uid=uid, token=token, level=0, is_new=True)

@app.post("/user/update-profile", summary="修改资料（昵称/头像/密码）")
def update_profile(body: UpdateProfileReq):
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. 查用户
            cur.execute("SELECT id, password_hash FROM users WHERE mobile=%s", (body.mobile,))
            u = cur.fetchone()
            if not u:
                raise HTTPException(status_code=404, detail="用户不存在")

            # 2. 改密码逻辑（若填写）
            if body.new_password:
                if not body.old_password:
                    raise HTTPException(status_code=400, detail="请提供旧密码")
                if not verify_pwd(body.old_password, u["password_hash"]):
                    raise HTTPException(status_code=400, detail="旧密码错误")
                new_hash = hash_pwd(body.new_password)
                cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, u["id"]))

            # 3. 改昵称/头像（非空才更新）
            if body.name is not None:
                cur.execute("UPDATE users SET name=%s WHERE id=%s", (body.name, u["id"]))
            if body.avatar_path is not None:
                cur.execute("UPDATE users SET avatar_path=%s WHERE id=%s", (body.avatar_path, u["id"]))

            conn.commit()
    return {"msg": "ok"}

# -------------- 自助注销（软删除） --------------
@app.post("/user/self-delete", summary="用户自助注销账号")
def self_delete(body: SelfDeleteReq):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, password_hash, status FROM users WHERE mobile=%s", (body.mobile,))
            u = cur.fetchone()
            if not u:
                raise HTTPException(status_code=404, detail="用户不存在")

            # 验证密码
            if not verify_pwd(body.password, u["password_hash"]):
                raise HTTPException(status_code=403, detail="密码错误")

            # 写审计日志（使用枚举的整数值）
            cur.execute(
                "INSERT INTO audit_log(user_id, op_type, old_val, new_val, reason) VALUES (%s,'SELF_DELETE',%s,%s,%s)",
                (u["id"], int(u["status"]), int(UserStatus.DELETED), body.reason)
            )
            # 更新状态为 DELETED
            cur.execute("UPDATE users SET status=%s WHERE id=%s", (int(UserStatus.DELETED), u["id"]))
            conn.commit()
    return {"msg": "账号已注销"}


# -------------- 后台冻结/解冻 --------------
@app.put("/user/freeze", summary="后台冻结用户")
def freeze_user(body: FreezeReq):
    if body.admin_key != "admin2025":
        raise HTTPException(status_code=403, detail="后台口令错误")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, status FROM users WHERE mobile=%s", (body.mobile,))
            u = cur.fetchone()
            if not u:
                raise HTTPException(status_code=404, detail="用户不存在")
            if u["status"] == UserStatus.DELETED:
                raise HTTPException(status_code=400, detail="账号已注销，无法冻结")

            new_status = UserStatus.FROZEN.value  # 使用枚举的值
            if u["status"] == new_status:
                return {"msg": "已是冻结状态"}

            cur.execute(
                "INSERT INTO audit_log(user_id, op_type, old_val, new_val, reason) VALUES (%s,'FREEZE',%s,%s,%s)",
                (u["id"], u["status"], new_status, body.reason)
            )
            cur.execute("UPDATE users SET status=%s WHERE id=%s", (new_status, u["id"]))
            conn.commit()
    return {"msg": "已冻结"}


@app.put("/user/unfreeze", summary="后台解冻用户")
def unfreeze_user(body: FreezeReq):
    if body.admin_key != "admin2025":
        raise HTTPException(status_code=403, detail="后台口令错误")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, status FROM users WHERE mobile=%s", (body.mobile,))
            u = cur.fetchone()
            if not u:
                raise HTTPException(status_code=404, detail="用户不存在")

            new_status = UserStatus.NORMAL.value  # 使用枚举的值
            if u["status"] == new_status:
                return {"msg": "已是正常状态"}

            cur.execute(
                "INSERT INTO audit_log(user_id, op_type, old_val, new_val, reason) VALUES (%s,'UNFREEZE',%s,%s,%s)",
                (u["id"], u["status"], new_status, body.reason)
            )
            cur.execute("UPDATE users SET status=%s WHERE id=%s", (new_status, u["id"]))
            conn.commit()
    return {"msg": "已解冻"}




# -------------- 找回密码（自助） --------------
@app.post("/user/reset-password", summary="找回密码（短信验证）")
def reset_password(body: ResetPwdReq):
    # 1. 短信验证码校验（先 mock）
    if body.sms_code != "111111":
        raise HTTPException(status_code=400, detail="验证码错误")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (body.mobile,))
            u = cur.fetchone()
            if not u:
                raise HTTPException(status_code=404, detail="手机号未注册")

            # 2. 重置密码
            new_hash = hash_pwd(body.new_password)
            cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, u["id"]))
            conn.commit()
    return {"msg": "密码已重置"}


# -------------- 后台重置密码（无需旧密码） --------------
@app.put("/admin/user/reset-pwd", summary="后台重置用户密码")
def admin_reset_password(body: AdminResetPwdReq):
    if body.admin_key != "admin2025":
        raise HTTPException(status_code=403, detail="后台口令错误")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (body.mobile,))
            u = cur.fetchone()
            if not u:
                raise HTTPException(status_code=404, detail="用户不存在")

            new_hash = hash_pwd(body.new_password)
            cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, u["id"]))
            # 写审计
            cur.execute(
                "INSERT INTO audit_log(user_id, op_type, old_val, new_val, reason) VALUES (%s,'RESET_PWD',0,1,'后台重置')",
                (u["id"],)
            )
            conn.commit()
    return {"msg": "密码已重置"}






@app.post("/user/upload-avatar", summary="上传头像")
def upload_avatar(mobile: str = Form(...), file: UploadFile = File(...)):
    # 这里调用 OSS / 本地存储，返回 URL
    url = upload_to_oss(file)  # 伪函数
    return {"avatar_path": url}

@app.post("/user/upgrade", summary="升 1 星")
def upgrade(mobile: str):
    try:
        new_lv = UserService.upgrade_one_star(mobile)
        return {"new_level": new_lv}
    except ValueError as e:
        _err(str(e))

@app.post("/user/set-level", summary="后台调星")
def set_level(body: SetLevelReq):
    try:
        old = UserService.set_level(body.mobile, body.new_level, body.reason)
        return {"old_level": old, "new_level": body.new_level}
    except ValueError as e:
        _err(str(e))

@app.get("/user/info", summary="用户详情（个人中心）", response_model=UserInfoResp)
def user_info(mobile: str = Query(..., description="用户手机号")):
    """
    在原基础上补充：
    - 推荐码
    - 直推人数
    - 团队总人数（含间接，最多 6 层）
    - 资产余额
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. 基础资料
            cur.execute(
                "SELECT id, mobile, name, avatar_path, member_level, referral_code "
                "FROM users WHERE mobile=%s AND status != %s",  # 添加状态检查
                (mobile, UserStatus.DELETED.value)  # 使用枚举的值
            )
            u = cur.fetchone()
            if not u:
                raise HTTPException(status_code=404, detail="用户不存在或已注销")

            # 2. 推荐人信息（保持旧逻辑）
            cur.execute(
                "SELECT ru.mobile, ru.name, ru.member_level "
                "FROM user_referrals r JOIN users ru ON ru.id=r.referrer_id "
                "WHERE r.user_id=%s",
                (u["id"],)
            )
            referrer = cur.fetchone()

            # 3. 直推人数
            cur.execute(
                "SELECT COUNT(*) AS c FROM user_referrals WHERE referrer_id=%s",
                (u["id"],)
            )
            direct_count = cur.fetchone()["c"]

            # 4. 团队总人数（含间接，最多 6 层）
            cur.execute(
                """
                WITH RECURSIVE team AS (
                    SELECT id, 0 AS layer FROM users WHERE id=%s
                    UNION ALL
                    SELECT r.user_id, t.layer + 1
                    FROM user_referrals r
                    JOIN team t ON t.id = r.referrer_id
                    WHERE t.layer < 6
                )
                SELECT COUNT(*) - 1 AS c FROM team
                """,
                (u["id"],)
            )
            team_total = cur.fetchone()["c"]

            # 5. 资产余额
            cur.execute(
                "SELECT member_points, merchant_points, withdrawable_balance "
                "FROM users WHERE id=%s",
                (u["id"],)
            )
            assets = cur.fetchone()

    return UserInfoResp(
        uid=u["id"],
        mobile=u["mobile"],
        name=u["name"],
        avatar_path=u["avatar_path"],
        member_level=u["member_level"],
        referral_code=u["referral_code"],
        direct_count=direct_count,
        team_total=team_total,
        assets={
            "member_points": assets["member_points"],
            "merchant_points": assets["merchant_points"],
            "withdrawable_balance": assets["withdrawable_balance"]
        },
        referrer=referrer
    )

@app.get("/user/list", summary="分页列表+筛选")
def user_list(
    id_start: Optional[int] = Query(None, ge=1),
    id_end: Optional[int] = Query(None, ge=1),
    level_start: int = Query(0, ge=0, le=6),
    level_end: int = Query(6, ge=0, le=6),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
):
    if level_start > level_end or (id_start is not None and id_end is not None and id_start > id_end):
        _err("区间左值不能大于右值")
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
            cur.execute(f"SELECT COUNT(*) AS c FROM users {sql_where}", args[:-2])
            total = cur.fetchone()["c"]
            return {"rows": rows, "total": total, "page": page, "size": size}

@app.post("/user/bind-referrer", summary="绑定推荐人")
def bind_referrer(mobile: str, referrer_mobile: str):
    try:
        UserService.bind_referrer(mobile, referrer_mobile)
        return {"msg": "ok"}
    except ValueError as e:
        _err(str(e))

@app.get("/user/refer-direct", summary="直推列表")
def refer_direct(mobile: str, page: int = 1, size: int = 10):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                _err("用户不存在")
            cur.execute("SELECT COUNT(*) AS c FROM user_referrals WHERE referrer_id=%s", (u["id"],))
            total = cur.fetchone()["c"]
            cur.execute("""
                SELECT u.id, u.mobile, u.name, u.member_level, u.created_at
                FROM user_referrals r
                JOIN users u ON u.id = r.user_id
                WHERE r.referrer_id=%s
                ORDER BY u.created_at DESC
                LIMIT %s OFFSET %s
            """, (u["id"], size, (page - 1) * size))
            rows = cur.fetchall()
            return {"rows": rows, "total": total, "page": page, "size": size}

@app.get("/user/refer-team", summary="团队列表（递归）")
def refer_team(mobile: str, max_layer: int = Query(6, ge=1, le=6)):
    with get_conn() as conn:
        with conn.cursor() as cur:
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
            return {"rows": rows}

# -------------- 地址模块 --------------
@app.post("/address", summary="新增地址")
def address_add(body: AddressReq):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (body.mobile,))
            u = cur.fetchone()
            if not u:
                _err("用户不存在")
            addr_id = AddressService.add_address(
                u["id"], body.name, body.phone, body.province, body.city,
                body.district, body.detail, body.is_default, body.addr_type
            )
            return {"addr_id": addr_id}

@app.put("/address/default", summary="把已有地址设为默认")
def set_default_addr(addr_id: int, mobile: str = Query(...)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. 校验地址归属
            cur.execute("SELECT user_id FROM addresses WHERE id=%s", (addr_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="地址不存在")
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u or u["id"] != row["user_id"]:
                raise HTTPException(status_code=403, detail="地址不属于当前用户")

            # 2. 先清默认
            cur.execute("UPDATE addresses SET is_default=0 WHERE user_id=%s", (u["id"],))
            # 3. 再设默认
            cur.execute("UPDATE addresses SET is_default=1 WHERE id=%s", (addr_id,))
            conn.commit()
    return {"msg": "ok"}

@app.delete("/address/{addr_id}", summary="删除地址")
def delete_addr(addr_id: int, mobile: str = Query(...)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 1. 校验归属
            cur.execute("SELECT user_id FROM addresses WHERE id=%s", (addr_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="地址不存在")
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u or u["id"] != row["user_id"]:
                raise HTTPException(status_code=403, detail="地址不属于当前用户")

            # 2. 删除
            cur.execute("DELETE FROM addresses WHERE id=%s", (addr_id,))
            conn.commit()
    return {"msg": "ok"}


@app.get("/address/list", summary="地址列表")
def address_list(mobile: str, page: int = 1, size: int = 5):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                _err("用户不存在")
            rows = AddressService.get_address_list(u["id"], page, size)
            return {"rows": rows}

@app.post("/address/return", summary="商家设置退货地址")
def return_addr_set(body: AddressReq):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (body.mobile,))
            u = cur.fetchone()
            if not u:
                _err("商家不存在")
            addr_id = AddressService.add_address(
                u["id"], body.name, body.phone, body.province, body.city,
                body.district, body.detail, is_default=True, addr_type="return"
            )
            return {"addr_id": addr_id}

@app.get("/address/return", summary="查看退货地址")
def return_addr_get(mobile: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                _err("商家不存在")
            addr = AddressService.get_default_address(u["id"])
            if not addr:
                _err("未设置退货地址")
            return addr

# -------------- 积分模块 --------------
@app.post("/points", summary="增减积分")
def points(body: PointsReq):
    try:
        # 先根据手机号拿到 user_id
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE mobile=%s", (body.mobile,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="用户不存在")
                user_id = row["id"]
        add_points(user_id, body.points_type, body.amount, body.reason)
        return {"msg": "ok"}
    except ValueError as e:
        _err(str(e))

@app.get("/points/balance", summary="积分余额")
def points_balance(mobile: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT member_points, merchant_points, withdrawable_balance FROM users WHERE mobile=%s", (mobile,))
            row = cur.fetchone()
            if not row:
                _err("用户不存在")
            return row

@app.get("/points/log", summary="积分流水")
def points_log(
    mobile: str,
    points_type: str = Query("member", pattern="^(member|merchant)$"),
    page: int = 1,
    size: int = 10,
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                _err("用户不存在")
            where, args = ["user_id=%s", "points_type=%s"], [u["id"], points_type]
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
            cur.execute(f"SELECT COUNT(*) AS c FROM points_log WHERE {sql_where}", args[:-2])
            total = cur.fetchone()["c"]
            return {"rows": rows, "total": total, "page": page, "size": size}

# -------------- 团队奖励模块 --------------
@app.get("/reward/list", summary="我的团队奖励")
def reward_list(mobile: str, page: int = 1, size: int = 10):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE mobile=%s", (mobile,))
            u = cur.fetchone()
            if not u:
                _err("用户不存在")
            rows = TeamRewardService.get_reward_list_by_user(u["id"], page, size)
            return {"rows": rows}

@app.get("/reward/by-order/{order_id}", summary="按订单查看奖励")
def reward_by_order(order_id: int):
    rows = TeamRewardService.get_reward_by_order(order_id)
    return {"rows": rows}

# -------------- 荣誉董事模块 --------------
@app.post("/director/try-promote", summary="晋升荣誉董事")
def director_try_promote(user_id: int):
    ok = DirectorService.try_promote(user_id)
    return {"success": ok}

@app.get("/director/is", summary="是否荣誉董事")
def director_is(user_id: int):
    return {"is_director": DirectorService.is_director(user_id)}

@app.get("/director/dividend", summary="分红明细")
def director_dividend(user_id: int, page: int = 1, size: int = 10):
    rows = DirectorService.get_dividend_detail(user_id, page, size)
    return {"rows": rows}

@app.get("/director/list", summary="所有活跃董事")
def director_list(page: int = 1, size: int = 10):
    rows = DirectorService.list_all_directors(page, size)
    return {"rows": rows}

@app.post("/director/calc-week", summary="手动触发周分红（仅内部）")
def director_calc_week(period: datetime.date):
    total_paid = DirectorService.calc_week_dividend(period)
    return {"total_paid": total_paid}

# -------------- 审计日志 --------------
@app.get("/audit", summary="等级变动审计")
def audit_list(mobile: Optional[str] = None, page: int = 1, size: int = 10):
    where, args = "", []
    if mobile:
        where = "WHERE u.mobile=%s"
        args.append(mobile)
    with get_conn() as conn:
        with conn.cursor() as cur:
            count_sql = f"SELECT COUNT(*) AS c FROM audit_log a JOIN users u ON u.id=a.user_id {where}"
            cur.execute(count_sql, args)
            total = cur.fetchone()["c"]
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
            return {"rows": rows, "total": total, "page": page, "size": size}

@app.post("/user/grant-merchant", summary="后台赋予商户身份")
def grant_merchant(mobile: str, admin_key: str = Query(..., description="后台口令")):
    if admin_key != "gm2025":
        raise HTTPException(status_code=403, detail="口令错误")
    if UserService.grant_merchant(mobile):
            return {"msg": "已赋予商户身份"}
    raise HTTPException(status_code=404, detail="用户不存在")

@app.get("/user/is-merchant", summary="查询是否商户")
def is_merchant(mobile: str):
    return {"is_merchant": UserService.is_merchant(mobile)}