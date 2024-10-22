import asyncio
import random

from fastapi import HTTPException
from chatgpt.databases import get_rt_at_key_list
from chatgpt.refreshToken import rt2ac
from utils.Logger import logger
from utils.config import authorization_list
import chatgpt.globals as globals
from utils.get_ak import get_ak



def get_req_token(req_token):
    if req_token in authorization_list:
        if len(globals.token_list) - len(globals.error_token_list) > 0:
            globals.count += 1
            globals.count %= len(globals.token_list)
            while globals.token_list[globals.count] in globals.error_token_list:
                globals.count += 1
                globals.count %= len(globals.token_list)
            return globals.token_list[globals.count]
        else:
            return None
    else:
        return req_token

async def is_valid_model(data, type):
    allowed_models_plus = ['o1-mini', 'o1-preview', 'gpt-4o', 'gpt-4o-mini', 'gpt-4o-2024-08-06', 'gpt-4o-mini-2024-07-18', 'gpt-4', 'gpt-4-turbo', 'gpt-4-turbo-2024-04-09', 'gpt-4-turbo-2024-07-18']
    allowed_models_basic = ['gpt-4o', 'gpt-4o-mini', 'gpt-4o-2024-08-06', 'gpt-4o-mini-2024-07-18']
    model = data.get('model')
    if not type == "plus":
        # 检查非 plus 用户模型限制
        return model in allowed_models_basic
    return model in allowed_models_plus

#保存rt
async def write_at(rt, account_id):
    with open('data/at.txt', 'a') as f:
        f.write("rt:"+rt+" account_id:"+account_id+"\n")

async def verify_token(req_token: str, data) -> tuple:
    if not req_token:
        if authorization_list:
            logger.error("使用空 token 进行未授权访问。")
            raise HTTPException(status_code=401, detail="未授权：缺少 token。")
        else:
            return None

    if req_token.startswith("sk-"):
        # 处理密钥 token
        try:
            req_token, token_type, account_id = await get_rt_at_key_list(req_token)
        except Exception as e:
            logger.error(f"获取 token 列表时出错：{e}")
            raise HTTPException(status_code=500, detail="内部服务器错误。")

        if not await is_valid_model(data, token_type):
            raise HTTPException(status_code=403, detail="此用户不允许使用该模型。")

        tokens = req_token.split(",") if "," in req_token else [req_token]
        selected_token = random.choice(tokens)

        # 如果未提供 account_id，使用默认的 account_id
        account_id = account_id or "1111"
        return selected_token, account_id

    else:
        # 处理普通 token
        try:
            if len(req_token) < 100:
                req_token = await get_ak(req_token)
        except Exception as e:
            logger.error(f"获取 AK 时出错：{e}")
            raise HTTPException(status_code=500, detail="内部服务器错误。")

        if not await is_valid_model(data, "normal"):
            raise HTTPException(status_code=403, detail="此用户不允许使用该模型。")

        access_token = req_token

        try:
            await write_at(access_token, "1111")
        except Exception as e:
            logger.error(f"写入访问令牌时出错：{e}")
            raise HTTPException(status_code=500, detail="内部服务器错误。")

        return access_token, "1111"

async def refresh_all_tokens(force_refresh=False):
    for token in globals.token_list:
        if len(token) == 45:
            try:
                await asyncio.sleep(2)
                await rt2ac(token, force_refresh=force_refresh)
            except HTTPException:
                pass
    logger.info("All tokens refreshed.")
