from utils.Logger import logger
import aiomysql
import redis.asyncio as redis
import json
from utils.config import DB_CONFIG, REDIS_CONFIG
from utils.get_ak import get_ak

# Redis 键名前缀
AUTH_KEY_REDIS_PREFIX = 'auth_key:'
# Redis 缓存过期时间（秒）
AUTH_KEY_CACHE_EXPIRE = 3600  # 1小时

# 创建 Redis 连接池
async def get_redis_pool():
    return redis.Redis(**REDIS_CONFIG)

async def get_rt_at_key_list(auth_key):
    redis_key = f"{AUTH_KEY_REDIS_PREFIX}{auth_key}"
    redis_pool = await get_redis_pool()
    # 尝试从 Redis 获取
    data_str = await redis_pool.get(redis_key)
    if data_str:
        data = json.loads(data_str)
        rt_at_key = data["rt_at_key"]
        type = data["type"]
        if rt_at_key:
            # Redis 中的数据是字节，需要解码为字符串
            logger.info(f"从 Redis 获取到 rt_at_key: {rt_at_key} 和 type: {type} for auth_key: {auth_key}")
            return rt_at_key, type
    else:
        # Redis 中没有缓存，从 MySQL 获取
        pool = await aiomysql.create_pool(**DB_CONFIG)
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 使用参数化查询以防止SQL注入
                await cur.execute("SELECT rt_at_key, type FROM chat2api.auth_keys WHERE auth_key = %s", (auth_key,))
                result = await cur.fetchone()
                if result:
                    rt_at_key = result[0]
                    type = result[1]
                    logger.info(f"从 MySQL 获取到 rt_at_key: {rt_at_key} 和 type: {type} for auth_key: {auth_key}")
                else:
                    rt_at_key = None
                    type = None
        pool.close()
        await pool.wait_closed()
        if rt_at_key:
            #如果rt_at_key是以,分割的列表则进行循环取access_token
            if "," in rt_at_key:
                rt_at_key_list = rt_at_key.split(",")
                access_token_list = []
                for rt_at_key in rt_at_key_list:
                    if len(rt_at_key) < 100:
                        access_token = await get_ak(rt_at_key)
                        access_token_list.append(access_token)
                rt_at_key = ",".join(access_token_list)
            else:
                if len(rt_at_key) < 100:
                    rt_at_key = await get_ak(rt_at_key)
            data = {
                "rt_at_key": rt_at_key,
                "type": type
            }
            await redis_pool.set(redis_key, json.dumps(data), ex = 43200)
            logger.info(f"将 rt_at_key 存入 Redis: {json.dumps(data)} for auth_key: {auth_key}")
            return rt_at_key, type
        else:
            return None, None
    redis_pool.close()
    await redis_pool.wait_closed()

#删除Mysql数据库及redis中的缓存中的token
async def delete_rt_at_key(redis_pool, auth_key):
    print("删除Mysql数据库及redis中的缓存中的token:" + auth_key)
    redis_key = f"{AUTH_KEY_REDIS_PREFIX}{auth_key}"
    await redis_pool.delete(redis_key)
    pool = await aiomysql.create_pool(**DB_CONFIG)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM chat2api.auth_keys WHERE auth_key = %s", (auth_key,))
            deleted_rows = cur.rowcount
            await conn.commit()  # 提交事务
            print(f"删除的行数: {deleted_rows}")
    pool.close()
    await pool.wait_closed()