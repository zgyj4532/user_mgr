| 序号   | 场景描述                       | 完整命令示例（手机号/参数按需替换）                                                                                     |
|------|----------------------------|--------------------------------------------------------------------------------------------------------|
| 1.   | **初始化用户管理库表**（含地址、积分、审计字段） | `uv run main.py init-db`                                                                               |
| 2.   | **注册新用户**（可带昵称 & 推荐人）      | `uv run main.py register 13800000001 pass123 -n 张三 -r 13800000000`                                     |
| 3.   | **用户登录**（返回等级/票据）          | `uv run main.py login 13800000001 pass123`                                                             |
| 4.   | **升 1 星（不可逆）**             | `uv run main.py upgrade 13800000001`                                                                   |
| 5.   | **绑定/换绑推荐人**               | `uv run main.py referrer 13800000002 13800000001`                                                      |
| 6.   | **后台手动调星 0-6 星**           | `uv run main.py set-level 13800000001 6 --reason "活动奖励"`                                               |
| 7.   | **分页列表 + ID/星级区间筛选**       | `uv run main.py user-list --level-start 1 --level-end 5 --id-start 10 --id-end 100 --size 20 --page 1` |
| 8.   | **查询用户详情 & 直推推荐人**         | `uv run main.py user-info 13800000001`                                                                 |
| 9.   | **查看等级变动审计日志**             | `uv run main.py audit-list --mobile 13800000001 --page 1`                                              |
| 10.  | **一键清空所有业务数据**（保留表）        | `uv run main.py clear-data`                                                                            |
| 11.  | **新增收货地址**（可设默认）           | `uv run main.py address-add 13800000001 张三 13800000001 广东省 深圳市 南山区 "科技园科兴科学园A栋" --default`             |
| 12.  | **查看收货地址列表**（分页）           | `uv run main.py address-list 13800000001 --page 1 --size 5`                                            |
| 13.  | **查当前积分余额**（仅购买商品变动）       | `uv run main.py points-balance 13800000001`                                                            |
| 14.  | **查看积分流水**（可按订单筛选/用户类型）    | `uv run main.py points-log 13800000001 --order 202506150001 --page 1`                                  |
| 15.  | **查看直推列表（一级）**             | `uv run main.py refer-direct 13800000001 --page 1`                                                     |
| 16.  | **统计团队人数（≤N 层）**           | `uv run main.py refer-team 13800000001 --max-layer 6`                                                  |
| 17.  | **统计团队各星级人数**              | `uv run main.py refer-star 13800000001 --max-layer 6`                                                  |
| 18   | **注册新商家**（一步完成注册+身份=1）     | `uv run main.py register 13800000002 pass123 -n 王老板 --merchant`                                        ||
| 19   | **商家设置/更新退货地址**（唯一）        | `uv run main.py return-addr-set 13800000002 王老板 13800000002 广东省 深圳市 南山区 "科技园科兴科学园 A-1F 退货部"`           |
| 20   | **查看商家退货地址**               | `uv run main.py return-addr-get 13800000002`                                                           |
| 21 ? | **更新用户头像路径**（前端上传后）        | `uv run main.py avatar-set 13800000001 /avatar/2025/1201/abc123.jpg`                                   |
| 22 ? | **获取用户头像路径**               | `uv run main.py avatar-get 13800000001`                                                                |
| 23   | **查看积分流水（商家类型）**           | `uv run main.py points-log 13800000002 --type merchant --page 1`                                       |
| 24   | **查看个人团队奖励列表**（获奖人视角）      | `uv run main.py reward-list 13800000001 --page 1 --size 10`                                            |
| 25   | **按订单查看团队奖励明细**            | `uv run main.py reward-by-order 202506150001`                                                          |
| 26   |                            |           uvicorn main:app --reload
                                                                                             |
