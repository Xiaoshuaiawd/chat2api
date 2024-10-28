import asyncio
import json
import os
import random
import re

import ua_generator
from fastapi import HTTPException

import chatgpt.globals as globals
from chatgpt.refreshToken import rt2ac
from utils.Logger import logger
from utils.config import authorization_list, random_token
from chatgpt.databases import get_rt_at_key_list

os.environ['PYTHONHASHSEED'] = '0'
random.seed(0)


def get_req_token(req_token, seed=None):
    available_token_list = list(set(globals.token_list) - set(globals.error_token_list))
    length = len(available_token_list)
    if seed and length > 0:
        req_token = globals.token_list[hash(seed) % length]
        while req_token in globals.error_token_list:
            req_token = random.choice(globals.token_list)
        return req_token

    if req_token in authorization_list:
        if len(available_token_list) > 0:
            if random_token:
                req_token = random.choice(available_token_list)
                return req_token
            else:
                globals.count += 1
                globals.count %= length
                return available_token_list[globals.count]
        else:
            return None
    else:
        return req_token


def get_ua(req_token):
    user_agent = globals.user_agent_map.get(req_token, {})
    user_agent = {k.lower(): v for k, v in user_agent.items()}
    if not user_agent:
        if not req_token:
            ua = ua_generator.generate(device='desktop', browser=('chrome', 'edge'), platform=('windows', 'macos'))
            return {
                "user-agent": ua.text,
                "sec-ch-ua-platform": ua.platform,
                "sec-ch-ua": ua.ch.brands,
                "sec-ch-ua-mobile": ua.ch.mobile,
                "impersonate": random.choice(globals.impersonate_list),
            }
        else:
            ua = ua_generator.generate(device='desktop', browser=('chrome', 'edge'), platform=('windows', 'macos'))
            user_agent = {
                "user-agent": ua.text,
                "sec-ch-ua-platform": ua.platform,
                "sec-ch-ua": ua.ch.brands,
                "sec-ch-ua-mobile": ua.ch.mobile,
                "impersonate": random.choice(globals.impersonate_list),
            }
            globals.user_agent_map[req_token] = user_agent
            with open(globals.USER_AGENTS_FILE, "w", encoding="utf-8") as f:
                f.write(json.dumps(globals.user_agent_map, indent=4))
            return user_agent
    else:
        return user_agent


async def match_model(model, allowed_models):
    for allowed_model in allowed_models:
        if '*' in allowed_model:
            # 将通配符转换为正则表达式
            pattern = re.escape(allowed_model).replace(r'\*', '.*')
            if re.match(pattern, model):
                return True
        elif model == allowed_model:
            return True
    return False

async def is_valid_model(data, type):
    allowed_models_plus = [
        'o1-mini', 'o1-preview', 'gpt-4o', 'gpt-4o-mini', 'gpt-4o-2024-08-06', 
        'gpt-4o-mini-2024-07-18', 'gpt-4', 'gpt-4-turbo', 'gpt-4-turbo-2024-04-09', 
        'gpt-4-turbo-2024-07-18', 'gpt-4-gizmo-g-*'
    ]
    allowed_models_basic = [
        'gpt-4o', 'gpt-4o-mini', 'gpt-4o-2024-08-06', 'gpt-4o-mini-2024-07-18',
        'gpt-4-gizmo-g-*'
    ]
    model = data.get('model')
    
    if type == "plus":
        return await match_model(model, allowed_models_plus)
    else:
        return await match_model(model, allowed_models_basic)

async def verify_token(req_token: str, data) -> tuple:
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
        raise HTTPException(status_code=403, detail="请使用用户系统提供的key进行请求")


async def refresh_all_tokens(force_refresh=False):
    for token in list(set(globals.token_list) - set(globals.error_token_list)):
        if len(token) == 45:
            try:
                await asyncio.sleep(2)
                await rt2ac(token, force_refresh=force_refresh)
            except HTTPException:
                pass
    logger.info("All tokens refreshed.")
