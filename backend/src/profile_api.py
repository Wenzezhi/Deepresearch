from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from urllib.parse import urlsplit
from openai import OpenAI
from config import Configuration


class ProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    model_id: str = Field(min_length=1, max_length=200)
    api_key: str | None = None
    max_tokens: int = Field(default=8192, ge=1, le=1048576)
    timeout: float = Field(default=120, ge=1, le=600)

    @field_validator('name', 'base_url', 'model_id')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if not value: raise ValueError('不能为空')
        return value

    @field_validator('base_url')
    @classmethod
    def valid_url(cls, value):
        url = urlsplit(value)
        if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('请输入有效的 HTTP(S) API 基础地址，不要包含密钥或查询参数')
        return value.rstrip('/')


def resolve_config(store, profile_id=None, search_api=None):
    overrides = {'search_api': search_api} if search_api is not None else {}
    if profile_id:
        try: p = store.profile(profile_id)
        except KeyError: raise HTTPException(404, '模型配置不存在，请重新选择')
        overrides.update(llm_provider='custom', llm_base_url=p['base_url'], llm_model_id=p['model_id'], llm_api_key=p['api_key'] or 'not-required', llm_max_tokens=p['max_tokens'], llm_timeout=p['timeout'])
    return Configuration.from_env(overrides)


def router(store):
    api = APIRouter(prefix='/model-profiles')

    @api.get('')
    def list_profiles(): return store.profiles()

    @api.post('', status_code=201)
    def create_profile(payload: ProfileInput): return store.save_profile(payload.model_dump())

    @api.put('/{identifier}')
    def update_profile(identifier: str, payload: ProfileInput):
        try: return store.save_profile(payload.model_dump(), identifier)
        except KeyError: raise HTTPException(404, '模型配置不存在')

    @api.delete('/{identifier}')
    def delete_profile(identifier: str):
        try: store.delete_profile(identifier)
        except KeyError: raise HTTPException(404, '模型配置不存在')
        return {'ok': True}

    @api.post('/{identifier}/test')
    def test_profile(identifier: str):
        try: p = store.profile(identifier)
        except KeyError: raise HTTPException(404, '模型配置不存在')
        try:
            with OpenAI(base_url=p['base_url'], api_key=p['api_key'] or 'not-required', timeout=min(p['timeout'],30), max_retries=0) as client:
                r = client.chat.completions.create(model=p['model_id'], messages=[{'role':'user','content':'Reply only OK.'}], max_tokens=min(p['max_tokens'],512))
            if not r.choices or not r.choices[0].message.content:
                return {'ok':False, 'message':'接口可连接，但未返回正文，请检查模型或输出额度'}
            return {'ok':True, 'message':'连接成功，模型已返回正文'}
        except Exception as exc:
            status = getattr(exc,'status_code',None)
            # Do not expose SDK errors/headers, which can include credentials.
            return {'ok':False, 'message':f'连接失败：HTTP {status}' if status else '连接失败：请检查地址、网络和超时时间'}
    return api
