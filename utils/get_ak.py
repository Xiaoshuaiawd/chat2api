from utils.Logger import logger
import requests
import asyncio

# 异步获取 ak
async def get_ak(refresh_token):
    url = "https://token.oaifree.com/api/auth/refresh"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "refresh_token": refresh_token
    }
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, requests.post, url, data, headers)
        if response.status_code == 200:
            return response.json()['access_token']
        else:
            return None
    except requests.RequestException as e:
        logger.error(f"获取 ak 时发生错误: {e}")
        return None