import os
import pymysql
from dotenv import load_dotenv


load_dotenv()

CFG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "rootpass"),
    "db": os.getenv("MYSQL_DATABASE", "userdb"),
    "charset": "utf8mb4",
    "autocommit": True,

}
Wechat_ID = {
        "wechat_app_id": os.getenv("WECHAT_APP_ID", ""),
        "wechat_app_secret": os.getenv("WECHAT_APP_SECRET", ""),
}
def get_conn():
    return pymysql.connect(**CFG, cursorclass=pymysql.cursors.DictCursor)

# 在 config.py 末尾追加
CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    mobile VARCHAR(30) NOT NULL UNIQUE,
    password_hash CHAR(60) NOT NULL,
    name VARCHAR(100),
    member_level TINYINT NOT NULL DEFAULT 0,
    referral_id BIGINT UNSIGNED,
    referral_code VARCHAR(6) NOT NULL UNIQUE,
    member_points BIGINT NOT NULL DEFAULT 0,
    merchant_points BIGINT NOT NULL DEFAULT 0,
    withdrawable_balance BIGINT NOT NULL DEFAULT 0,
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
    points_type ENUM('member', 'merchant') NOT NULL DEFAULT 'member',
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
    addr_type ENUM('shipping', 'return') NOT NULL DEFAULT 'shipping',
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

# 荣誉董事表
CREATE_DIRECTORS = """
CREATE TABLE IF NOT EXISTS directors (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    status ENUM('pending','active','frozen') NOT NULL DEFAULT 'pending',
    dividend_amount DECIMAL(14,2) NOT NULL DEFAULT 0.00,   -- 累计已得分红
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activated_at DATETIME NULL,
    UNIQUE KEY uk_user (user_id),
    INDEX idx_status (status)
);
"""

# 每次周分红明细
CREATE_DIRECTOR_DIVIDENDS = """
CREATE TABLE IF NOT EXISTS director_dividends (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    period_date DATE NOT NULL,          -- 分红周期（自然周）
    dividend_amount DECIMAL(14,2) NOT NULL,
    new_sales DECIMAL(14,2) NOT NULL,   -- 本周平台新业绩
    weight DECIMAL(8,4) NOT NULL,       -- 个人加权系数
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_period (user_id, period_date)
);
"""

# 为了快速判定“直推 3 个六星 + 团队 10 个六星”，在 users 表加两个派生字段
ALTER_USERS_FOR_DIRECTOR = """
ALTER TABLE users
  ADD COLUMN six_director TINYINT NOT NULL DEFAULT 0 COMMENT '直推六星人数' AFTER member_level,
  ADD COLUMN six_team     INT  NOT NULL DEFAULT 0 COMMENT '团队六星人数' AFTER six_director;
"""