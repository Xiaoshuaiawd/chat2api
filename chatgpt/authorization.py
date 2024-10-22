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

async def verify_token(req_token, data):
    if not req_token:
        if authorization_list:
            logger.error("Unauthorized with empty token.")
            raise HTTPException(status_code=401)
        else:
            return None
    else:
        if req_token.startswith("sk-"):
            if req_token.startswith("sk-"):
                req_token,type,account_id = await get_rt_at_key_list(req_token)
                if not await is_valid_model(data, type):
                    raise HTTPException(status_code=403, detail="Model not allowed for this user.")
                if "," in req_token:
                    req_token = req_token.split(",")[random.randint(0, len(req_token.split(",")) - 1)]
                if account_id:
                    await write_at(req_token, account_id)
                    access_token = req_token
                    return access_token, account_id
                else:
                    await write_at(req_token, "")
                    access_token = req_token
                    return access_token, "1111"
        else:
            if len(req_token) < 100:
                req_token = await get_ak(req_token)
            if not await is_valid_model(data, "normal"):
                raise HTTPException(status_code=403, detail="Model not allowed for this user.")
            access_token = req_token
            await write_at(access_token, "")
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
