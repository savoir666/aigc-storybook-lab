"""Local configuration. Secrets never cross the status/settings response."""
from pathlib import Path
from urllib.parse import urlparse
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data'
PROJECTS = DATA / 'projects'
DEFAULTS = {
    'TEXT_BASE_URL': 'https://open.bigmodel.cn/api/paas/v4',
    'TEXT_MODEL': 'glm-4.7-flash', 'TEXT_API_KEY': '',
    'IMAGE_BASE_URL': 'https://open.bigmodel.cn/api/paas/v4',
    'IMAGE_MODEL': 'cogview-3-flash', 'IMAGE_API_KEY': '', 'MODE': 'demo',
    'IMAGE_PROVIDER': 'cogview', 'WAN_BASE_URL': 'https://dashscope.aliyuncs.com',
    'WAN_MODEL': 'wan2.7-image-pro', 'WAN_API_KEY': '', 'WAN_SEED': '20261027',
    'WAN_FREE_TIER_CONFIRMED': 'false',
}
FREE_TEXT = {'glm-4.7-flash', 'glm-4-flash-250414', 'glm-4-flash'}
FREE_IMAGE = {'cogview-3-flash'}

def settings():
    return {**DEFAULTS, **{k: v for k, v in dotenv_values(ROOT / '.env').items() if k in DEFAULTS and v is not None}}

def public_settings():
    c = settings()
    return dict(text_base_url=c['TEXT_BASE_URL'], text_model=c['TEXT_MODEL'], text_key_set=bool(c['TEXT_API_KEY']),
                image_base_url=c['IMAGE_BASE_URL'], image_model=c['IMAGE_MODEL'], image_key_set=bool(c['WAN_API_KEY']) if c['IMAGE_PROVIDER']=='wan' else bool(c['IMAGE_API_KEY'] or c['TEXT_API_KEY']),
                mode=c['MODE'], free_only=True, image_provider=c['IMAGE_PROVIDER'],
                wan_base_url=c['WAN_BASE_URL'], wan_model=c['WAN_MODEL'], wan_key_set=bool(c['WAN_API_KEY']),
                wan_seed=int(c['WAN_SEED']), wan_free_tier_confirmed=c['WAN_FREE_TIER_CONFIRMED'].lower()=='true')

def update_settings(values: dict):
    pending = []
    for key, value in values.items():
        target = key.upper()
        if target not in DEFAULTS or value is None:
            continue
        if target.endswith('API_KEY') and not value:
            continue
        value = str(value).strip()
        if len(value) > 1000 or '\n' in value or '\r' in value:
            raise ValueError('配置格式无效。')
        if target.endswith('BASE_URL'):
            parsed = urlparse(value)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('模型地址必须是HTTPS地址，不能包含账号密码。')
            value = value.rstrip('/')
        if target == 'IMAGE_PROVIDER' and value not in {'cogview', 'wan'}:
            raise ValueError('图片服务必须选择cogview或wan。')
        if target == 'WAN_MODEL' and value not in {'wan2.7-image-pro', 'wan2.7-image'}:
            raise ValueError('只开放已核对的万相2.7图片模型。')
        if target == 'WAN_SEED' and (not value.isdigit() or not 0 <= int(value) <= 2147483647):
            raise ValueError('固定Seed必须为0到2147483647的整数。')
        if target == 'WAN_FREE_TIER_CONFIRMED':
            value = value.lower()
            if value not in {'true', 'false'}:
                raise ValueError('请确认免费额度和用完即停状态。')
        if target == 'MODE' and value not in {'demo', 'live'}:
            raise ValueError('模式必须是demo或live。')
        pending.append((target,value))
    for target,value in pending:
        set_key(str(ROOT / '.env'), target, value)
    return public_settings()

def require_free(kind: str):
    c = settings()
    if kind == 'image' and c['IMAGE_PROVIDER'] == 'wan':
        import re
        endpoint = urlparse(c['WAN_BASE_URL'])
        host = endpoint.hostname or ''
        allowed_host = host == 'dashscope.aliyuncs.com' or re.fullmatch(r'[a-z0-9-]+\.cn-beijing\.maas\.aliyuncs\.com', host)
        if endpoint.scheme != 'https' or not allowed_host or endpoint.username or endpoint.password or endpoint.path.rstrip('/') or endpoint.query or endpoint.fragment or endpoint.port not in {None,443}:
            raise ValueError('百炼地址必须是北京地域官方API Host。')
        if c['WAN_MODEL'] not in {'wan2.7-image-pro','wan2.7-image'}:
            raise ValueError('百炼图片模型未在已核对名单中。')
        if c['WAN_FREE_TIER_CONFIRMED'].lower() != 'true':
            raise ValueError('请先在百炼确认所选模型有剩余免费额度，并开启免费额度用完即停，再勾选本机确认。未确认不会发起图片请求。')
        if not c['WAN_API_KEY']:
            raise ValueError('请在创作设置的百炼图片区域填写API Key；不会将智谱密钥发送给百炼。')
        return {**c, 'IMAGE_MODEL':c['WAN_MODEL'], 'IMAGE_BASE_URL':c['WAN_BASE_URL'].rstrip('/')}, c['WAN_API_KEY']
    prefix = 'TEXT' if kind == 'text' else 'IMAGE'
    allowed = FREE_TEXT if kind == 'text' else FREE_IMAGE
    endpoint = urlparse(c[prefix + '_BASE_URL'])
    if endpoint.scheme != 'https' or endpoint.username or endpoint.password or endpoint.hostname != 'open.bigmodel.cn' or c[prefix + '_MODEL'].lower() not in allowed:
        raise ValueError('当前启用免费优先保护：只允许已核对的智谱免费模型。更换服务或付费模型前请先确认价格和授权。')
    key = c[prefix + '_API_KEY'] or (c['TEXT_API_KEY'] if prefix == 'IMAGE' else '')
    if not key:
        raise ValueError('尚未配置API密钥。请打开右上角“创作设置”，按指导创建并保存密钥；也可先体验本地示例。')
    return c, key
