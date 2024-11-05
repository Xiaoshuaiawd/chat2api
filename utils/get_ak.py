from utils.Logger import logger
import requests
import asyncio
from utils.config import proxy_url

# 异步获取 ak，添加代理支持
async def get_ak(refresh_token):
    url = "https://token.oaifree.com/api/auth/refresh"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "refresh_token": refresh_token
    }
    proxies = {
        "http": proxy_url,
        "https": proxy_url
    } if proxy_url else None  # 如果传入代理则使用，否则为 None

    try:
        loop = asyncio.get_event_loop()
        # 使用 run_in_executor 来异步调用带有代理的 requests.post
        response = await loop.run_in_executor(
            None, lambda: requests.post(url, data=data, headers=headers, proxies=proxies)
        )
        if response.status_code == 200:
            return response.json().get('access_token')
        else:
            logger.error(f"请求失败，状态码: {response.status_code}")
            return None
    except requests.RequestException as e:
        logger.error(f"获取 ak 时发生错误: {e}")
        return None