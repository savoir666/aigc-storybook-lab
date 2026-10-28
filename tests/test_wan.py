import asyncio,io,json
from pathlib import Path
import httpx
import pytest
from PIL import Image
from storybook import config,providers,storage
from storybook.models import StoryInput
from storybook.providers import ModelClient
from storybook.story import demo_story,make_project

@pytest.fixture
def wan(tmp_path,monkeypatch):
    for module in (config,providers):monkeypatch.setattr(module,'ROOT',tmp_path)
    for module in (config,providers,storage):monkeypatch.setattr(module,'DATA',tmp_path/'data')
    config.update_settings({'image_provider':'wan','wan_api_key':'wan-mock-secret','text_api_key':'text-mock-secret','wan_free_tier_confirmed':True})
    return tmp_path

def test_wan_requires_separate_key_and_quota_confirmation(wan):
    assert config.require_free('image')[1]=='wan-mock-secret'
    config.update_settings({'wan_free_tier_confirmed':False})
    with pytest.raises(ValueError,match='免费额度'):config.require_free('image')
    config.update_settings({'wan_free_tier_confirmed':True})
    (wan/'.env').write_text('IMAGE_PROVIDER=wan\nTEXT_API_KEY=text-mock-secret\nWAN_FREE_TIER_CONFIRMED=true\n',encoding='utf-8')
    with pytest.raises(ValueError,match='不会将智谱密钥'):config.require_free('image')

def test_wan_official_beijing_hosts_only(wan):
    for host in ('https://dashscope.aliyuncs.com.evil.example','https://dashscope-intl.aliyuncs.com','https://dashscope.aliyuncs.com/api','https://dashscope.aliyuncs.com?leak=1'):
        config.update_settings({'wan_base_url':host})
        with pytest.raises(ValueError,match='北京'):config.require_free('image')
    config.update_settings({'wan_base_url':'https://llm-test.cn-beijing.maas.aliyuncs.com'})
    assert config.require_free('image')[0]['IMAGE_MODEL']=='wan2.7-image-pro'

def test_invalid_seed_does_not_partially_save_secrets(wan):
    before=(wan/'.env').read_text(encoding='utf-8')
    with pytest.raises(ValueError):config.update_settings({'wan_api_key':'must-not-save','wan_seed':-1})
    assert (wan/'.env').read_text(encoding='utf-8')==before
    public=json.dumps(config.public_settings())
    assert 'wan-mock-secret' not in public and 'text-mock-secret' not in public

def test_wan_seed_reference_cache_and_proofs(wan):
    png=io.BytesIO();Image.new('RGB',(256,256),'orange').save(png,'PNG')
    reference=wan/'data/library/images/character-cute-v6-eyes.png';reference.parent.mkdir(parents=True);reference.write_bytes(png.getvalue())
    calls=[]
    def respond(request):
        if request.url.host=='images.example':
            assert 'Authorization' not in request.headers
            return httpx.Response(200,content=png.getvalue())
        payload=json.loads(request.content);calls.append(payload)
        assert request.url.path=='/api/v1/services/aigc/multimodal-generation/generation'
        assert request.headers['Authorization']=='Bearer wan-mock-secret'
        assert payload['parameters']['n']==1 and payload['parameters']['enable_sequential'] is False
        assert payload['input']['messages'][0]['content'][0]['image'].startswith('data:image/png;base64,')
        prompt=payload['input']['messages'][0]['content'][-1]['text']
        assert '地点与动作：' in prompt and '正文动作依据：' in prompt
        assert '不要白底' in prompt
        return httpx.Response(200,json={'request_id':'mock','output':{'choices':[{'message':{'content':[{'image':'https://images.example/scene.png'}]}}]}})
    async def run():
        params=StoryInput();p=make_project(demo_story(params),params,'mock');p['scenes']=p['scenes'][:2]
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            service=ModelClient(client);await service.images(p,wan/'case');assert len(calls)==2
            await service.images(p,wan/'case');assert len(calls)==2
            config.update_settings({'wan_seed':7});await service.images(p,wan/'case');assert len(calls)==4
            assert all(row['parameters']['seed']==20261027 for row in calls[:2])
        proof=json.loads((wan/'case/scene-01.proof.json').read_text(encoding='utf-8'))
        assert proof['seed']==7 and proof['reference_sha256'] and proof['automatic_replay'] is False
        assert 'wan-mock-secret' not in json.dumps(proof)
    asyncio.run(run())

def test_wan_failure_never_automatically_replays(wan):
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(503,json={'message':'temporary error'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(ValueError,match='503'):
                await ModelClient(client)._post('https://dashscope.aliyuncs.com/test','wan-mock-secret',{'model':'wan2.7-image-pro'},replay=False)
    asyncio.run(run());assert len(calls)==1
