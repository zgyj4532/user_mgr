import uuid
import pymysql
from config import Wechat_ID
import requests
import hashlib
from jose import jwt
import datetime
from fastapi import Request, HTTPException
from src.config import get_conn
from src.user_service import hash_pwd, UserStatus, _generate_code

# 微信小程序配置从环境变量读取，避免明文写入仓库
WECHAT_APP_ID = Wechat_ID.get("wechat_app_id", "")
WECHAT_APP_SECRET = Wechat_ID.get("wechat_app_secret", "")



async def wechat_login(request: Request):
    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
        raise HTTPException(status_code=500, detail="未配置微信小程序 AppId/Secret，请在 .env 中设置 WECHAT_APP_ID 与 WECHAT_APP_SECRET")

    # 确保 users 表存在 openid 字段（兼容旧库）
    ensure_openid_column()

    data = await request.json()
    code = data.get('code')
    nick_name = data.get('nickName')

    if not code or not nick_name:
        raise HTTPException(status_code=400, detail="缺少参数")

    # 调用微信接口，通过code换取openid和session_key
    url = f"https://api.weixin.qq.com/sns/jscode2session?appid={WECHAT_APP_ID}&secret={WECHAT_APP_SECRET}&js_code={code}&grant_type=authorization_code"
    response = requests.get(url)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="微信接口调用失败")

    wechat_data = response.json()
    print("微信接口返回：", wechat_data)
    openid = wechat_data.get('openid')
    session_key = wechat_data.get('session_key')

    if not openid or not session_key:
        raise HTTPException(status_code=500, detail="无法获取openid或session_key")

    # 检查用户是否已注册
    try:
        user = await check_user_by_openid(openid)
        if not user:
            # 注册新用户
            user_id = await register_user(openid, nick_name)
        else:
            user_id = user['id']
    except Exception as e:
        # 输出具体异常便于排查 400 问题（如字段缺失、唯一约束等）
        print("微信注册流程异常：", e)
        raise HTTPException(status_code=500, detail=f"微信注册失败: {e}")

    # 生成token并返回
    token = generate_token(user_id)
    return {
        "success": True,
        "user_id": user_id,
        "token": token
    }

async def check_user_by_openid(openid):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE openid=%s", (openid,))
            result = cur.fetchone()
            return result

def ensure_openid_column():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM users LIKE 'openid'")
            exists = cur.fetchone()
            if not exists:
                try:
                    cur.execute("ALTER TABLE users ADD COLUMN openid VARCHAR(64) UNIQUE")
                    conn.commit()
                except pymysql.err.InternalError as e:
                    if e.args[0] == 1060:  # 字段已存在
                        return
                    raise


async def register_user(openid, nick_name):
    """为微信用户创建账号，自动生成必填字段"""
    # 生成占位手机号，保证唯一
    mobile = f"wx_{openid[:20]}"
    pwd_hash = hash_pwd(uuid.uuid4().hex)

    with get_conn() as conn:
        with conn.cursor() as cur:
            # 唯一推荐码
            code = _generate_code()
            cur.execute("SELECT 1 FROM users WHERE referral_code=%s", (code,))
            while cur.fetchone():
                code = _generate_code()
                cur.execute("SELECT 1 FROM users WHERE referral_code=%s", (code,))

            # 确保占位手机号不冲突
            cur.execute("SELECT 1 FROM users WHERE mobile=%s", (mobile,))
            idx = 1
            base_mobile = mobile
            while cur.fetchone():
                mobile = f"{base_mobile}_{idx}"
                cur.execute("SELECT 1 FROM users WHERE mobile=%s", (mobile,))
                idx += 1

            cur.execute(
                "INSERT INTO users(openid, mobile, password_hash, name, member_points, merchant_points, withdrawable_balance, status, referral_code) "
                "VALUES (%s, %s, %s, %s, 0, 0, 0, %s, %s)",
                (openid, mobile, pwd_hash, nick_name, int(UserStatus.NORMAL), code)
            )
            return cur.lastrowid

def generate_token(user_id):
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    }
    token = jwt.encode(payload, "your_secret_key", algorithm="HS256")
    return token