import asyncio
import types
import warnings

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask

from chatgpt.ChatService import ChatService
from chatgpt.authorization import refresh_all_tokens
import chatgpt.globals as globals
from chatgpt.reverseProxy import chatgpt_reverse_proxy
from utils.Logger import logger
from utils.config import api_prefix, scheduled_refresh
from utils.retry import async_retry

warnings.filterwarnings("ignore")

app = FastAPI()
scheduler = AsyncIOScheduler()
templates = Jinja2Templates(directory="templates")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def app_start():
    if scheduled_refresh:
        scheduler.add_job(id='refresh', func=refresh_all_tokens, trigger='cron', hour=3, minute=0, day='*/4', kwargs={'force_refresh': True})
        scheduler.start()
        asyncio.get_event_loop().call_later(0, lambda: asyncio.create_task(refresh_all_tokens(force_refresh=False)))


async def to_send_conversation(request_data, req_token):
    chat_service = ChatService(req_token)
    try:
        await chat_service.set_dynamic_data(request_data)
        await chat_service.get_chat_requirements()
        return chat_service
    except HTTPException as e:
        await chat_service.close_client()
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        await chat_service.close_client()
        logger.error(f"Server error, {str(e)}")
        raise HTTPException(status_code=500, detail="Server error")


async def process(request_data, req_token):
    chat_service = await to_send_conversation(request_data, req_token)
    await chat_service.prepare_send_conversation()
    res = await chat_service.send_conversation()
    return chat_service, res


@app.post(f"/{api_prefix}/v1/chat/completions" if api_prefix else "/v1/chat/completions")
async def send_conversation(request: Request, req_token: str = Depends(oauth2_scheme)):
    try:
        request_data = await request.json()
        for message in request_data['messages']:
            # 检查 role 字段
            if message.get('role') == 'assistant':
                # 替换 role 为 user
                message['role'] = 'user'
                # 在 content 文本前添加 "assistant："
                message['content'] = f"assistant：{message['content']}"
            if message.get('role') == 'system':
                # 替换 role 为 user
                message['role'] = 'user'
                # 在 content 文本前添加 "assistant："
                message['content'] = f"system：{message['content']}"
    except Exception:
        raise HTTPException(status_code=400, detail={"error": "Invalid JSON body"})
    chat_service, res = await async_retry(process, request_data, req_token)
    try:
        if isinstance(res, types.AsyncGeneratorType):
            background = BackgroundTask(chat_service.close_client)
            return StreamingResponse(res, media_type="text/event-stream", background=background)
        else:
            background = BackgroundTask(chat_service.close_client)
            return JSONResponse(res, media_type="application/json", background=background)
    except HTTPException as e:
        await chat_service.close_client()
        if e.status_code == 500:
            logger.error(f"Server error, {str(e)}")
            raise HTTPException(status_code=500, detail="Server error")
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        await chat_service.close_client()
        logger.error(f"Server error, {str(e)}")
        raise HTTPException(status_code=500, detail="Server error")

@app.get(f"/{api_prefix}/v1/models" if api_prefix else "/v1/models")
async def models():
    models ={
            "data": [
                {
                "id": "gpt-4o",
                "object": "model",
                "created": 1626777600,
                "owned_by": "openai",
                "permission": [
                    {
                        "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                        "object": "model_permission",
                        "created": 1626777600,
                        "allow_create_engine": True,
                        "allow_sampling": True,
                        "allow_logprobs": True,
                        "allow_search_indices": False,
                        "allow_view": True,
                        "allow_fine_tuning": False,
                        "organization": "*",
                        "group": None,
                        "is_blocking": False
                    }
                ],
                "root": "gpt-4o",
                "parent": None
                },
                {
                    "id": "gpt-4o-mini",
                    "object": "model",
                    "created": 1626777600,
                    "owned_by": "openai",
                    "permission": [
                        {
                            "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                            "object": "model_permission",
                            "created": 1626777600,
                            "allow_create_engine": True,
                            "allow_sampling": True,
                            "allow_logprobs": True,
                            "allow_search_indices": False,
                            "allow_view": True,
                            "allow_fine_tuning": False,
                            "organization": "*",
                            "group": None,
                            "is_blocking": False
                        }
                    ],
                    "root": "gpt-4o-mini",
                    "parent": None
                },
                {
                    "id": "gpt-4o-2024-08-06",
                    "object": "model",
                    "created": 1626777600,
                    "owned_by": "openai",
                    "permission": [
                        {
                            "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                            "object": "model_permission",
                            "created": 1626777600,
                            "allow_create_engine": True,
                            "allow_sampling": True,
                            "allow_logprobs": True,
                            "allow_search_indices": False,
                            "allow_view": True,
                            "allow_fine_tuning": False,
                            "organization": "*",
                            "group": None,
                            "is_blocking": False
                        }
                    ],
                    "root": "gpt-4o-2024-08-06",
                    "parent": None
                },
                {
                    "id": "gpt-4o-mini-2024-07-18",
                    "object": "model",
                    "created": 1626777600,
                    "owned_by": "openai",
                    "permission": [
                        {
                            "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                            "object": "model_permission",
                            "created": 1626777600,
                            "allow_create_engine": True,
                            "allow_sampling": True,
                            "allow_logprobs": True,
                            "allow_search_indices": False,
                            "allow_view": True,
                            "allow_fine_tuning": False,
                            "organization": "*",
                            "group": None,
                            "is_blocking": False
                        }
                    ],
                    "root": "gpt-4o-mini-2024-07-18",
                    "parent": None
                },
                {
                    "id": "o1-mini",
                    "object": "model",
                    "created": 1626777600,
                    "owned_by": "openai",
                    "permission": [
                        {
                            "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                            "object": "model_permission",
                            "created": 1626777600,
                            "allow_create_engine": True,
                            "allow_sampling": True,
                            "allow_logprobs": True,
                            "allow_search_indices": False,
                            "allow_view": True, 
                            "allow_fine_tuning": False,
                            "organization": "*",
                            "group": None,
                            "is_blocking": False
                        }
                    ],
                    "root": "o1-mini",
                    "parent": None
                },
                {
                    "id": "o1-mini-2024-07-18",
                    "object": "model",
                    "created": 1626777600,
                    "owned_by": "openai",
                    "permission": [
                        {
                            "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                            "object": "model_permission",
                            "created": 1626777600,
                            "allow_create_engine": True,
                            "allow_sampling": True,
                            "allow_logprobs": True,
                            "allow_search_indices": False,
                            "allow_view": True,
                            "allow_fine_tuning": False,
                            "organization": "*",
                            "group": None,
                            "is_blocking": False
                        }
                    ],
                    "root": "o1-mini-2024-07-18",
                    "parent": None
                },
                {
                    "id": "o1-preview",
                    "object": "model",
                    "created": 1626777600,
                    "owned_by": "openai",
                    "permission": [
                        {
                            "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                            "object": "model_permission",
                            "created": 1626777600,
                            "allow_create_engine": True,
                            "allow_sampling": True,
                            "allow_logprobs": True,
                            "allow_search_indices": False,
                            "allow_view": True,
                            "allow_fine_tuning": False,
                            "organization": "*",
                            "group": None,
                            "is_blocking": False
                        }   
                    ],
                    "root": "o1-preview",
                    "parent": None
                },
                {
                    "id": "o1-preview-2024-07-18",
                    "object": "model",
                    "created": 1626777600,
                    "owned_by": "openai",
                    "permission": [
                        {
                            "id": "modelperm-LwHkVFn8AcMItP432fKKDIKJ",
                            "object": "model_permission",
                            "created": 1626777600,
                            "allow_create_engine": True,
                            "allow_sampling": True,
                            "allow_logprobs": True,
                            "allow_search_indices": False,
                            "allow_view": True,
                            "allow_fine_tuning": False,
                            "organization": "*",
                            "group": None,
                            "is_blocking": False
                        }
                    ],
                    "root": "o1-preview-2024-07-18",
                    "parent": None
                }
            ],
            "success": True
        }
    return models

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"])
async def reverse_proxy(request: Request, path: str):
    return await chatgpt_reverse_proxy(request, path)
