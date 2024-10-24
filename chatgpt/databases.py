from utils.Logger import logger
import aiomysql
import redis.asyncio as redis
import json
import asyncio
from utils.config import DB_CONFIG, REDIS_CONFIG
from utils.get_ak import get_ak

# Redis 键名前缀
AUTH_KEY_REDIS_PREFIX = 'auth_key:'

# Redis 缓存过期时间（秒）
AUTH_KEY_CACHE_EXPIRE = 43200  # 12小时

# 创建 Redis 连接池 (全局单例)
redis_pool = None
mysql_pool = None

# 获取 Redis 连接池，确保全局只创建一次
async def get_redis_pool():
    global redis_pool
    if not redis_pool:
        redis_pool = redis.Redis(**REDIS_CONFIG)
    return redis_pool

# 获取 MySQL 连接池，确保全局只创建一次
async def get_mysql_pool():
    global mysql_pool
    if not mysql_pool:
        mysql_pool = await aiomysql.create_pool(**DB_CONFIG)
    return mysql_pool

# 获取 rt_at_key 列表
async def get_rt_at_key_list(auth_key):
    redis_key = f"{AUTH_KEY_REDIS_PREFIX}{auth_key}"
    redis_pool = await get_redis_pool()
    # 尝试从 Redis 获取缓存
    data_str = await redis_pool.get(redis_key)
    if data_str:
        data = json.loads(data_str)
        rt_at_key = data.get("rt_at_key")
        type = data.get("type")
        account_id = data.get("account_id")
        if rt_at_key:
            logger.info(f"从 Redis 获取到 rt_at_key: {rt_at_key} type: {type} account_id: {account_id} for auth_key: {auth_key}")
            return rt_at_key, type, account_id
    else:
        # Redis 中没有缓存，从 MySQL 获取
        mysql_pool = await get_mysql_pool()
        async with mysql_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT rt_at_key, type, account_id FROM chat2api.auth_keys WHERE auth_key = %s", (auth_key,))
                result = await cur.fetchone()
                if result:
                    rt_at_key, type, account_id = result
                    account_id = account_id if account_id else None
                    logger.info(f"从 MySQL 获取到 rt_at_key: {rt_at_key} type: {type} account_id: {account_id} for auth_key: {auth_key}")
                else:
                    return None, None, None

        if rt_at_key:
            # 如果 rt_at_key 是以 "," 分割的列表则进行处理
            if "," in rt_at_key:
                rt_at_key_list = rt_at_key.split(",")
                access_token_list = []
                for rt_at_key_item in rt_at_key_list:
                    if len(rt_at_key_item) < 100:
                        access_token = await get_ak(rt_at_key_item)
                        if access_token is not None:
                            access_token_list.append(access_token)
                        else:
                            logger.warning(f"get_ak 返回 None for key: {rt_at_key_item}")
                    else:
                        access_token_list.append(rt_at_key_item)
                # 过滤掉任何可能的 None 值
                access_token_list = [token for token in access_token_list if token is not None]
                rt_at_key = ",".join(access_token_list)
            else:
                if len(rt_at_key) < 100:
                    rt_at_key = await get_ak(rt_at_key)
                    if rt_at_key is None:
                        logger.warning(f"get_ak 返回 None for key: {rt_at_key}")
                # 这里也需要检查 rt_at_key 是否为 None
            data = {
                "rt_at_key": rt_at_key,
                "type": type,
                "account_id": account_id
            }
            await redis_pool.set(redis_key, json.dumps(data), ex=AUTH_KEY_CACHE_EXPIRE)
            logger.info(f"将 rt_at_key 存入 Redis: {json.dumps(data)} for auth_key: {auth_key}")
            await redis_pool.close()  # 关闭 Redis 连接
            return rt_at_key, type, account_id
    await redis_pool.close()  # 关闭 Redis 连接
    return None, None, None

# 在程序退出时手动关闭连接池
async def close_pools():
    if redis_pool:
        await redis_pool.close()
    if mysql_pool:
        mysql_pool.close()
        await mysql_pool.wait_closed()