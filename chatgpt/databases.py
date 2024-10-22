from utils.Logger import logger
import aiomysql
import redis.asyncio as redis
import json
from utils.config import DB_CONFIG, REDIS_CONFIG
from utils.get_ak import get_ak
import asyncio
from typing import Optional, Tuple

# Redis 键名前缀
AUTH_KEY_REDIS_PREFIX = 'auth_key:'
# Redis 缓存过期时间（秒）
AUTH_KEY_CACHE_EXPIRE = 43200  # 12小时

# Global variables for connection pools
_redis_pool: Optional[redis.Redis] = None
_mysql_pool: Optional[aiomysql.Pool] = None
_pool_lock = asyncio.Lock()

# Locks to prevent cache stampede per auth_key
_key_locks = {}

async def get_redis_pool() -> redis.Redis:
    global _redis_pool
    if _redis_pool is None:
        async with _pool_lock:
            if _redis_pool is None:
                _redis_pool = redis.Redis(**REDIS_CONFIG)
                logger.info("Initialized Redis connection pool.")
    return _redis_pool

async def get_mysql_pool() -> aiomysql.Pool:
    global _mysql_pool
    if _mysql_pool is None:
        async with _pool_lock:
            if _mysql_pool is None:
                _mysql_pool = await aiomysql.create_pool(**DB_CONFIG)
                logger.info("Initialized MySQL connection pool.")
    return _mysql_pool

async def get_lock_for_key(auth_key: str) -> asyncio.Lock:
    """Get a lock object for a specific auth_key to prevent cache stampede."""
    if auth_key not in _key_locks:
        _key_locks[auth_key] = asyncio.Lock()
    return _key_locks[auth_key]

async def get_rt_at_key_list(auth_key: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    redis_key = f"{AUTH_KEY_REDIS_PREFIX}{auth_key}"
    redis_pool = await get_redis_pool()

    # Attempt to get data from Redis
    data_str = await redis_pool.get(redis_key)
    if data_str:
        try:
            data = json.loads(data_str)
            rt_at_key = data.get("rt_at_key")
            type_ = data.get("type")
            account_id = data.get("account_id")
            if rt_at_key:
                logger.info(f"Retrieved from Redis: rt_at_key={rt_at_key}, type={type_}, account_id={account_id} for auth_key={auth_key}")
                return rt_at_key, type_, account_id
        except json.JSONDecodeError:
            logger.warning(f"Failed to decode JSON from Redis for key {redis_key}. Proceeding to fetch from MySQL.")

    # Acquire per-key lock to prevent multiple DB fetches
    key_lock = await get_lock_for_key(auth_key)
    async with key_lock:
        # Double-check if another coroutine has already set the cache
        data_str = await redis_pool.get(redis_key)
        if data_str:
            try:
                data = json.loads(data_str)
                rt_at_key = data.get("rt_at_key")
                type_ = data.get("type")
                account_id = data.get("account_id")
                if rt_at_key:
                    logger.info(f"Retrieved from Redis after waiting: rt_at_key={rt_at_key}, type={type_}, account_id={account_id} for auth_key={auth_key}")
                    return rt_at_key, type_, account_id
            except json.JSONDecodeError:
                logger.warning(f"Failed to decode JSON from Redis for key {redis_key} after waiting.")

        # Fetch from MySQL
        mysql_pool = await get_mysql_pool()
        async with mysql_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT rt_at_key, type, account_id FROM chat2api.auth_keys WHERE auth_key = %s",
                    (auth_key,)
                )
                result = await cur.fetchone()
                if result:
                    rt_at_key, type_, account_id = result
                    account_id = account_id or None
                    logger.info(f"Retrieved from MySQL: rt_at_key={rt_at_key}, type={type_}, account_id={account_id} for auth_key={auth_key}")
                else:
                    rt_at_key = type_ = account_id = None
                    logger.warning(f"No data found in MySQL for auth_key={auth_key}")

        if rt_at_key:
            # Process rt_at_key
            if "," in rt_at_key:
                rt_at_key_list = rt_at_key.split(",")
                access_token_list = []
                tasks = [
                    get_ak(token) if len(token) < 100 else asyncio.sleep(0, result=token)
                    for token in rt_at_key_list
                ]
                results = await asyncio.gather(*tasks)
                rt_at_key = ",".join(results)
            else:
                if len(rt_at_key) < 100:
                    rt_at_key = await get_ak(rt_at_key)

            # Prepare data to cache
            data = {
                "rt_at_key": rt_at_key,
                "type": type_,
                "account_id": account_id
            }

            # Cache the data in Redis
            await redis_pool.set(redis_key, json.dumps(data), ex=AUTH_KEY_CACHE_EXPIRE)
            logger.info(f"Cached in Redis: {data} for auth_key={auth_key}")

            return rt_at_key, type_, account_id
        else:
            return None, None, None

# Optional: Close connection pools gracefully on application shutdown
async def close_pools():
    global _redis_pool, _mysql_pool
    if _redis_pool:
        await _redis_pool.close()
        await _redis_pool.wait_closed()
        logger.info("Closed Redis connection pool.")
    if _mysql_pool:
        _mysql_pool.close()
        await _mysql_pool.wait_closed()
        logger.info("Closed MySQL connection pool.")