"""Python HTTP model calls: free-model guard, cache, validation and bounded retries."""
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import httpx
from PIL import Image
from .config import ROOT, DATA, FREE_TEXT, require_free
from .storage import log_event, write_json
from .story import normalize_story, prompt_messages, compact_story

_semaphore = asyncio.Semaphore(1)

def extract_json(raw: str):
    text = raw.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        index = next((i for i, char in enumerate(text) if char in '{['), None)
        if index is not None:
            try:
                value, _ = decoder.raw_decode(text[index:])
                return value
            except json.JSONDecodeError:
                pass  # Never mistake a nested array for the malformed root.
        raise ValueError('模型没有返回合法JSON，请重试或更换Prompt策略。')

class ModelClient:
    def __init__(self, client=None, text_model=None):
        if text_model is not None and str(text_model).lower() not in FREE_TEXT:
            raise ValueError('模型覆盖必须属于免费文本模型白名单。')
        self.text_model = str(text_model).lower() if text_model else None
        self.client = client
        self.last_response_text = ""
        self.last_model = None

    async def _post(self, url, key, payload, replay=True):
        owned = self.client is None
        client = self.client or httpx.AsyncClient(timeout=httpx.Timeout(180, connect=25))
        try:
            for attempt in range(3 if replay else 1):
                try:
                    async with _semaphore:
                        response = await asyncio.wait_for(client.post(url, headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}, json=payload), timeout=180)
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < 2 and replay:
                        log_event({'kind': 'retry', 'model': payload.get('model'), 'status': response.status_code, 'attempt': attempt+1})
                        await asyncio.sleep((8, 20)[attempt] if response.status_code == 429 else 2 ** attempt * 2)
                        continue
                    if response.status_code >= 400:
                        try:
                            body = response.json()
                            message = body.get('error', {}).get('message', body.get('message', response.reason_phrase))
                        except (ValueError, AttributeError):
                            message = response.reason_phrase
                        message = str(message).replace(key, '[已隐藏密钥]')[:240]
                        raise ValueError(f'模型服务返回{response.status_code}：{message}')
                    return response.json()
                except (asyncio.TimeoutError, httpx.ReadTimeout) as exc:
                    log_event({'kind':'timeout','model':payload.get('model'),'automatic_replay':False})
                    raise ValueError('模型单次生成超过180秒或读取超时；未自动重复长请求。已有产物保留，可稍后重试。') from exc
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt == 2 or not replay:
                        raise ValueError('连接模型服务超时或网络不可用。请检查网络和模型地址后重试。') from exc
                    await asyncio.sleep(2 ** attempt)
        finally:
            if owned:
                await client.aclose()

    async def chat_json(self, messages, cache=True):
        config, key = require_free('text')
        if self.text_model:
            config = {**config, 'TEXT_MODEL':self.text_model}
        self.last_response_text = ''
        self.last_model = config['TEXT_MODEL']
        payload = {'model': config['TEXT_MODEL'], 'messages': messages, 'temperature': 0.7, 'max_tokens': 24000 if config['TEXT_MODEL'].lower() == 'glm-4.7-flash' else 16000,
                   'response_format': {'type': 'json_object'}}
        if config['TEXT_MODEL'].lower() == 'glm-4.7-flash':
            payload['thinking'] = {'type': 'disabled'}
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        path = DATA / 'cache' / f'text-{digest}.json'
        if cache and path.exists():
            log_event({'kind': 'text', 'model': config['TEXT_MODEL'], 'cache_hit': True, 'request_hash': digest})
            return json.loads(path.read_text(encoding='utf-8'))
        result = await self._post(config['TEXT_BASE_URL'] + '/chat/completions', key, payload)
        try:
            content = result['choices'][0]['message']['content']
            self.last_response_text = content if isinstance(content, str) else ''
            write_json(DATA / 'responses' / f'text-{digest}.json', {'model':config['TEXT_MODEL'], 'request_hash':digest, 'finish_reason':result['choices'][0].get('finish_reason'), 'usage':result.get('usage',{}), 'content':content})
            value = extract_json(content)
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError('模型返回结构异常，未找到故事内容。') from exc
        if not isinstance(value, dict):
            raise ValueError('模型JSON的根节点必须是对象。')
        write_json(path, value)
        log_event({'kind': 'text', 'model': config['TEXT_MODEL'], 'cache_hit': False, 'request_hash': digest, 'usage': result.get('usage', {})})
        return value

    async def story(self, params, context='', extra_messages=None):
        messages = prompt_messages(params, context) + list(extra_messages or [])
        value = None
        def checked(value):
            story = normalize_story(value)
            if len({d['character'] for scene in story['scenes'] for d in scene['dialogues'] if d['text'].strip()}) < 3:
                raise ValueError('必须至少三个实际说话角色；角色表有伙伴不等于伙伴已发声，请为伙伴补全独立对白。')
            actual = sum(len(d['text']) for scene in story['scenes'] for d in scene['dialogues'])
            minimum = {'short':650, 'medium':900, 'long':1100}[params.length]
            if actual < minimum:
                raise ValueError(f'配音正文只有{actual}字，必须扩写到至少{minimum}字。请将6幕逐幕扩写：每幕旁白180汉字以上、主角和伙伴各70汉字以上；保持完整JSON对象，不要只给大纲。')
            return compact_story(story, {'short':1000,'medium':1400,'long':1900}[params.length])
        try:
            value = await self.chat_json(messages)
            return checked(value), messages
        except (ValueError, TypeError) as first:
            raw = self.last_response_text or (json.dumps(value, ensure_ascii=False) if value is not None else '')
            if not raw:
                raise
            repair = messages + [{'role':'assistant', 'content':raw[:90000]},
                                 {'role':'user', 'content':'上一次输出格式不完整或字段未通过校验。请修复并重新输出一个完整JSON对象，根节点必须同时包含title、characters、scenes、moral；characters和scenes才是数组。不要解释，不要只输出数组。故事保持6幕、至少3个说话角色，完整结束JSON，并严格满足下述长度检查。错误摘要：'+str(first)[:500]}]
            return checked(await self.chat_json(repair, cache=True)), repair

    async def images(self, project, project_dir, log=None):
        config, key = require_free('image')
        from .story import FOX, STYLE
        folder = Path(project_dir)
        folder.mkdir(parents=True, exist_ok=True)
        proofs = []
        for i, scene in enumerate(project['scenes']):
            # Some valid model outputs repeat character-only visual_prompt fields.
            # Always ground the illustration in the actual scene and its action.
            scene_brief = (f'第{i+1}幕《{scene.get("title", "")}》。'
                           f'地点与动作：{scene.get("description", "")}。'
                           f'正文动作依据：{scene.get("text", "")[:650]}。')
            prompt = ('画完整的故事场景插画，环境和道具必须具体可见。'+scene_brief+
                      '采用中远景叙事构图，背景环境至少占画面一半，表现正在发生的动作；不要白底、留白底人物设定图或站成一排的角色合影。'
                      f'本故事设定：{project["inputs"].get("setting", "")}。'
                      f'{STYLE} 固定主角外观：{FOX} 主角名字{project["inputs"]["name"]}。'
                      f'其他角色外观：' + '; '.join(c['name'] + ':' + c['appearance'] for c in project['characters'] if c['role'] != 'narrator') +
                      f'。补充视觉要求：{scene["visual_prompt"]}。所有场景保持角色服装、脸和画风完全一致。'
                      '本幅必须表现的情节：'+scene_brief)
            review_path=folder/'image-review.json'
            if review_path.is_file():
                review=json.loads(review_path.read_text(encoding='utf-8'))
                note=review.get('scene_notes',{}).get(str(scene.get('scene_id',i+1)),'')
                if note:prompt += '。本幕图像审查后的明确修正要求（优先遵守）：'+str(note)
            wan = config.get('IMAGE_PROVIDER') == 'wan'
            request_body = {'model':config['IMAGE_MODEL'],'prompt':prompt[:4000],'size':'1024x1024'}
            reference_hash = None
            if wan:
                import base64
                reference = ROOT/'data/library/images/character-cute-v6-eyes.png'
                content = []
                if reference.is_file():
                    reference_bytes = reference.read_bytes()
                    reference_hash = hashlib.sha256(reference_bytes).hexdigest()
                    content.append({'image':'data:image/png;base64,'+base64.b64encode(reference_bytes).decode()})
                    prompt = '图1是主角身份参考。保持它的圆脸、大眼睛、奶油白脸颊、耳朵、围巾和唯一一条尾巴；保留主角身份，把它画进以下故事场景，动作和环境以当前场景为准，不要只重复正面肖像。'+prompt
                content.append({'text':prompt[:5000]})
                request_body = {'model':config['IMAGE_MODEL'],'input':{'messages':[{'role':'user','content':content}]},
                                'parameters':{'size':'1K','n':1,'seed':int(config['WAN_SEED']),'enable_sequential':False,'thinking_mode':True,'watermark':True}}
            digest = hashlib.sha256(json.dumps(request_body,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            dest = folder / f'scene-{i+1:02}.png'
            marker = folder / f'scene-{i+1:02}.proof.json'
            old = json.loads(marker.read_text(encoding='utf-8')) if marker.exists() else {}
            if old.get('prompt_hash') == digest and dest.exists() and old.get('sha256') == hashlib.sha256(dest.read_bytes()).hexdigest():
                proof = old
                if log: log(f'第{i+1}幕命中图片缓存。')
            else:
                if log: log(f'正在通过{config["IMAGE_MODEL"]}生成第{i+1}/{len(project["scenes"])}幕插画。')
                if wan:
                    result = await self._post(config['IMAGE_BASE_URL']+'/api/v1/services/aigc/multimodal-generation/generation',key,request_body,replay=False)
                else:
                    result = await self._post(config['IMAGE_BASE_URL']+'/images/generations',key,request_body)
                try:
                    if wan:
                        entries = result['output']['choices'][0]['message']['content']
                        entry = {'url':next(e['image'] for e in entries if e.get('image'))}
                    else:
                        entry = result['data'][0]
                    if entry.get('b64_json'):
                        import base64
                        raw = base64.b64decode(entry['b64_json'], validate=True)
                    else:
                        url = entry['url']
                        parsed = urlparse(url)
                        if parsed.scheme != 'https' or parsed.hostname in {'localhost', '127.0.0.1', '::1'}:
                            raise ValueError('图片服务返回了不安全的下载地址。')
                        download_owned = self.client is None
                        download = self.client or httpx.AsyncClient(timeout=90, follow_redirects=True)
                        try:
                            response = await download.get(url)
                            response.raise_for_status()
                            raw = response.content
                        finally:
                            if download_owned:
                                await download.aclose()
                    if len(raw) > 25_000_000:
                        raise ValueError('返回图片过大。')
                    import io
                    image = Image.open(io.BytesIO(raw))
                    image.convert('RGB').save(dest, 'PNG')
                except (KeyError, IndexError, StopIteration, httpx.HTTPError, OSError) as exc:
                    raise ValueError('图片生成结果下载或校验失败，请重试。') from exc
                proof = {'source': 'image_api', 'model': config['IMAGE_MODEL'], 'prompt': prompt, 'prompt_hash': digest,
                         'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
                         'provider':'wan' if wan else 'cogview','request_parameters':request_body.get('parameters',{'size':'1024x1024'}),
                         'seed':int(config['WAN_SEED']) if wan else None,'reference_sha256':reference_hash,
                         'consistency_scheme':'detailed_appearance_and_fixed_seed' if wan else 'appearance_prompt_only',
                         'request_id':result.get('request_id'),'automatic_replay':not wan}
                if wan:
                    write_json(folder/f'scene-{i+1:02}.response.json',result)
                write_json(marker, proof)
                log_event({'kind': 'image', 'model': config['IMAGE_MODEL'], 'project_id': project['id'], 'scene_id': i+1, 'prompt_hash': digest})
            scene['image_url'] = f'/files/projects/{project["id"]}/{dest.name}'
            scene['image_source'] = 'image_api'
            proofs.append(proof)
        project['cover_url'] = project['scenes'][0]['image_url']
        project['generation_proof'] = proofs
        project['status'] = 'images_ready'
        return project
