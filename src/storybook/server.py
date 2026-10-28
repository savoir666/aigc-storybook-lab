"""Loopback-only application serving the eight-week AIGC practice."""
import asyncio
import copy
import io
import json
import re
import traceback
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from .config import ROOT, DATA, PROJECTS, public_settings, update_settings
from .models import StoryInput, Instruction, AgentRequest, CompareRequest
from .storage import now, new_id, save_project, load_project, list_projects, project_dir, write_json
from .story import demo_story, make_project, revise_demo, prompt_messages, normalize_story, STRATEGIES, THEMES
from .providers import ModelClient
from .retrieval import AssetSearch
from .agent import run_agent
from .evidence import write_manifest, verify_manifest
from .media import render_demo_images, generate_audio, render_video, render_pdf

JOBS = {}
TASKS = set()
BUSY = set()
searcher = AssetSearch(ROOT)

def seed_projects():
    PROJECTS.mkdir(parents=True, exist_ok=True)
    for theme, name in [('forest', '小栗'), ('space', '小满'), ('ocean', '小橘')]:
        pid = 'sample-' + theme
        if (project_dir(pid) / 'project.json').exists():
            continue
        params = StoryInput(name=name, theme=theme)
        p = make_project(demo_story(params), params, pid)
        p['is_sample'] = True
        render_demo_images(p, project_dir(pid))
        render_pdf(p, project_dir(pid))
        save_project(p)
    jobs_dir = DATA / 'jobs'
    jobs_dir.mkdir(parents=True, exist_ok=True)
    for path in jobs_dir.glob('*.json'):
        try:
            job = json.loads(path.read_text(encoding='utf-8'))
            if job['status'] in {'queued', 'running', 'paused'}:
                job.update(status='failed', error='上次服务关闭中断了任务。已完成产物保留，请重新启动该操作。')
            JOBS[job['id']] = job
        except (KeyError, ValueError, OSError):
            continue

@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(seed_projects)
    yield
    for task in list(TASKS):
        task.cancel()

app = FastAPI(title='星芽故事屋', version='1.0.0', lifespan=lifespan)

@app.middleware('http')
async def local_guard(request: Request, call_next):
    host = request.headers.get('host', '').split(':')[0]
    if host not in {'127.0.0.1', 'localhost', 'testserver'}:
        return JSONResponse({'detail': '本项目仅允许本机访问。'}, status_code=403)
    origin = request.headers.get('origin')
    if request.method not in {'GET', 'HEAD', 'OPTIONS'} and origin and urlparse(origin).hostname not in {'127.0.0.1', 'localhost'}:
        return JSONResponse({'detail': '拒绝来自其他网站的操作请求。'}, status_code=403)
    result = await call_next(request)
    result.headers['X-Content-Type-Options'] = 'nosniff'
    result.headers['Referrer-Policy'] = 'no-referrer'
    if request.url.path.startswith('/api/'):
        result.headers['Cache-Control'] = 'no-store'
    return result

@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)

@app.exception_handler(FileNotFoundError)
async def missing(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=404)

def ensure_idle(pid):
    if pid in BUSY or any(j.get('project_id') == pid and j['status'] in {'queued', 'running', 'paused'} for j in JOBS.values()):
        raise HTTPException(409, '这本故事有正在执行的任务，请等待完成，或在Agent工作台介入当前任务。')

def job_log(job, message):
    job['logs'].append({'time': now(), 'message': str(message)})

def persist_job(job):
    write_json(DATA / 'jobs' / f'{job["id"]}.json', job)

def launch_job(pid, label, worker, **options):
    load_project(pid)
    ensure_idle(pid)
    jid = new_id()
    job = {'id': jid, 'project_id': pid, 'label': label, 'status': 'queued', 'progress': 0,
           'steps': [{'name': label, 'status': 'queued'}], 'logs': [], 'error': None, 'result': None, 'created_at': now(), **options}
    JOBS[jid] = job
    persist_job(job)
    async def run():
        job.update(status='running')
        job['steps'][0]['status'] = 'running'
        try:
            result = await worker(job)
            job.update(status='completed', progress=100)
            for step in job['steps']:
                step['status'] = 'completed'
            if result is not None:
                job['result'] = result
            job_log(job, label + '完成。')
        except asyncio.CancelledError:
            job.update(status='failed', error='服务关闭，任务已中断。')
            raise
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            # Do not serialize request headers, secrets or entire tracebacks to the UI.
            from .config import settings
            for key in ('TEXT_API_KEY', 'IMAGE_API_KEY', 'WAN_API_KEY'):
                secret = settings()[key]
                if secret:
                    message = message.replace(secret, '[已隐藏密钥]')
            job.update(status='failed', error=message[:800])
            job_log(job, '任务停止：' + message[:800])
            for step in job['steps']:
                if step['status'] == 'running':
                    step['status'] = 'failed'
        finally:
            job['finished_at'] = now()
            persist_job(job)
    task = asyncio.create_task(run())
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)
    return {'job_id': jid}

async def generate_story(params, pid=None, text_model=None):
    if params.mode == 'demo':
        p = make_project(demo_story(params), params, pid)
        render_demo_images(p, project_dir(p['id']))
    else:
        context = await asyncio.to_thread(searcher.search, params.interest + ' ' + THEMES[params.theme]['label'], 'template', 3)
        model_client = ModelClient(text_model=text_model)
        story, messages = await model_client.story(params, json.dumps(context['results'], ensure_ascii=False))
        p = make_project(story, params, pid)
        p['text_model'] = model_client.last_model
        write_json(project_dir(p['id']) / 'prompt-record.json', {'strategy': params.strategy, 'model':model_client.last_model, 'messages': messages, 'source': 'actual_api_request'})
    save_project(p)
    return p

async def revise_project(p, instruction):
    if p['mode'] == 'demo':
        result = revise_demo(p, instruction)
        render_demo_images(result, project_dir(result['id']))
    else:
        rename=re.fullmatch(r'(?:把)?(?:主角)?名字(?:改成|改为|换成|换为)[“\"\']?([\u4e00-\u9fffA-Za-z]{1,12})[”\"\']?[。！!]?\s*', instruction.strip())
        if rename:
            old=p['inputs']['name'];new=rename.group(1)
            params=StoryInput.model_validate({**p['inputs'],'name':new})
            source={k:p[k] for k in ['title','characters','scenes','moral','processing'] if k in p}
            source=json.loads(json.dumps(source,ensure_ascii=False).replace(old,new))
            result=make_project(source,params,p['id'])
            result.update(created_at=p['created_at'],text_model=p.get('text_model'),revision_instruction=instruction,revision_method='deterministic_name_replace')
            write_json(project_dir(p['id'])/'revision-record.json',{'method':'deterministic_name_replace','instruction':instruction,'old_name':old,'new_name':new,'source':'local edit of actual model story; no additional model request'})
            save_project(result)
            return result
        params = StoryInput.model_validate(p['inputs'])
        if any(word in instruction for word in ('结尾','最后一幕','最后一章')):
            # A local ending request must not shorten or rewrite the other scenes.
            source = {k:p[k] for k in ['title','characters','scenes','moral']}
            source = json.loads(json.dumps(source,ensure_ascii=False))
            messages = [
                {'role':'system','content':'你是低龄儿童绘本编辑，只修改结尾一幕。仅返回JSON对象{"scene":{"scene_id":6,"title":"","description":"","text":"","mood":"温柔","visual_prompt":"","dialogues":[{"character":"旁白","text":"","emotion":"温柔"}]},"moral":""}。保留所有既有角色名称与身份。结尾用分工、互相倾听、共同照料等具体行动体现合作；保留旁白并让三位故事人物分别直接发言。对白总计至少300汉字、旁白至少120汉字，避免重复口号。描述画面地点、道具和动作。不要改前五幕，不要添加新角色。'},
                {'role':'user','content':json.dumps({'instruction':instruction,'inputs':p['inputs'],'characters':p['characters'],'previous_scene_summaries':[{'title':x['title'],'description':x['description']} for x in p['scenes'][:-1]],'original_ending':p['scenes'][-1]},ensure_ascii=False)}]
            client = ModelClient(text_model='glm-4-flash-250414')
            for attempt in range(2):
                value = await client.chat_json(messages)
                try:
                    scene = value['scene'];scene['scene_id']=source['scenes'][-1]['scene_id']
                    scene['text']='\n'.join(row['text'] for row in scene['dialogues'])
                    if sum(len(row['text']) for row in scene['dialogues']) < 250:
                        raise ValueError('结尾对白正文不足250字，请扩写具体分工和照料经过。')
                    speakers={row['character'] for row in scene['dialogues']}
                    if '旁白' not in speakers or not {c['name'] for c in p['characters'] if c.get('role')!='narrator'} <= speakers:
                        raise ValueError('必须保留旁白及全部三位人物的独立发言。')
                    candidate={**source,'scenes':source['scenes'][:-1]+[scene],'moral':value.get('moral',source['moral'])}
                    normalized=normalize_story(candidate)
                    break
                except (ValueError,KeyError,TypeError) as exc:
                    if attempt:raise
                    messages += [{'role':'assistant','content':json.dumps(value,ensure_ascii=False)}, {'role':'user','content':'仅修复上述结尾JSON。检查问题：'+str(exc)[:400]}]
            result=make_project(normalized,params,p['id'])
            result.update(created_at=p['created_at'],text_model=p.get('text_model'),revision_instruction=instruction,revision_model='glm-4-flash-250414',revision_method='model_ending_patch')
            write_json(project_dir(p['id'])/'revision-record.json',{'model':'glm-4-flash-250414','instruction':instruction,'messages':messages,'source':'actual_api_request','scope':'last scene only; previous scenes preserved','previous_scene_count':len(source['scenes'])-1})
            save_project(result)
            return result
        messages = prompt_messages(params)
        source = {k:p[k] for k in ['title','characters','moral']}
        source['scenes'] = [{k:s[k] for k in ['scene_id','title','description','text','mood'] if k in s} for s in p['scenes']]
        messages.append({'role': 'user', 'content': '在以下现有故事正文上落实修改指令，保持完整JSON结构；重新给出完整配音对白和视觉Prompt，与正文同步。输入省略重复的对白副本以减少等待。指令：' + instruction + '\n现有故事：' + json.dumps(source, ensure_ascii=False)})
        # Revision must pass the same narration-length and schema checks as writing.
        story, messages = await ModelClient(text_model='glm-4-flash-250414').story(
            params, extra_messages=[messages[-1]])
        result = make_project(story, params, p['id'])
        write_json(project_dir(p['id'])/'revision-record.json', {'model':'glm-4-flash-250414','instruction':instruction,'messages':messages,'source':'actual_api_request'})
        result['revision_model'] = 'glm-4-flash-250414'
        result['text_model'] = p.get('text_model','glm-4-flash-250414')
        result['revision_instruction'] = instruction
        result['created_at'] = p['created_at']
    save_project(result)
    return result

@app.get('/api/status')
async def status():
    config = public_settings()
    return {'name': '星芽故事屋', 'version': '1.0.0', 'build': '20261028-scenes-voices-final', 'ready': True,
            'text_configured': config['text_key_set'], 'image_configured': config['image_key_set'],
            'tts': 'Microsoft Edge TTS · 真实网络配音', 'clip_ready': await asyncio.to_thread(lambda: searcher.clip_ready),
            'counts': {'projects': len(list_projects()), **searcher.counts}}

@app.get('/api/settings')
async def get_settings():
    return public_settings()

@app.post('/api/settings')
async def set_settings(values: dict):
    return update_settings(values)

@app.post('/api/settings/test')
async def test_settings():
    await ModelClient().chat_json([{'role':'user','content':'只返回JSON对象：{"ok":true}'}], cache=False)
    return {'ok': True, 'message': '免费文本模型连接成功。密钥仅保存在本机，图片任务会使用单独的文生图接口。'}

@app.get('/api/projects')
async def get_projects():
    return {'projects': list_projects()}

@app.post('/api/settings/check-image')
async def check_image_settings():
    from .config import require_free
    config, _ = require_free('image')
    return {'ok':True,'provider':config.get('IMAGE_PROVIDER','cogview'),'model':config['IMAGE_MODEL'],
            'message':'图片配置本机校验通过；尚未请求图片模型，不消耗图片额度。密钥有效性需实际生成一张后确认。'}

@app.post('/api/projects')
async def create_project(params: StoryInput):
    return {'project': await generate_story(params)}

@app.get('/api/projects/{pid}')
async def get_project(pid: str):
    return {'project': load_project(pid)}

@app.post('/api/projects/{pid}/revise')
async def revise(pid: str, req: Instruction):
    ensure_idle(pid)
    BUSY.add(pid)
    try:
        return {'project': await revise_project(load_project(pid), req.instruction)}
    finally:
        BUSY.discard(pid)

@app.post('/api/projects/{pid}/images')
async def images(pid: str):
    async def work(job):
        p = load_project(pid)
        if p['mode'] == 'demo':
            job_log(job, '本地示例采用程序绘制插画，未调用文生图API。')
            p = await asyncio.to_thread(render_demo_images, p, project_dir(pid))
        else:
            p = await ModelClient().images(p, project_dir(pid), lambda msg: job_log(job, msg))
        # New illustrations invalidate any older video and PDF links.
        p['video_url'] = p['pdf_url'] = ''
        p.pop('video_proof', None)
        save_project(p)
        return {'message': f'已生成{len(p["scenes"])}幕插画。', 'source': p['mode']}
    return launch_job(pid, '场景插画', work)

@app.post('/api/projects/{pid}/audio')
async def audio(pid: str):
    async def work(job):
        p = load_project(pid)
        p = await generate_audio(p, project_dir(pid), lambda msg: job_log(job, msg))
        p['video_url'] = ''
        p.pop('video_proof', None)
        save_project(p)
        return {'message': f'真实多角色配音已完成，共{p["audio_proof"]["duration"]:.1f}秒。', 'voices': p['audio_proof']['voices']}
    return launch_job(pid, '多角色有声书', work)

@app.post('/api/projects/{pid}/video')
async def video(pid: str):
    async def work(job):
        p = load_project(pid)
        p = await asyncio.to_thread(render_video, p, project_dir(pid), lambda msg: job_log(job, msg))
        save_project(p)
        return {'message': '绘本视频已导出，包含真实配音、背景音乐和同步字幕。', 'video': p.get('video_proof')}
    return launch_job(pid, '绘本视频', work)

@app.post('/api/projects/{pid}/agent')
async def agent(pid: str, req: AgentRequest):
    async def work(job):
        p = load_project(pid)
        async def write():
            job_log(job, '写作工具执行结构化故事生成；真实模式使用Python模型接口及缓存。')
            if p.get('text_model'):
                generated = await generate_story(StoryInput.model_validate(p['inputs']), pid, text_model=p['text_model'])
            else:
                generated = await generate_story(StoryInput.model_validate(p['inputs']), pid)
            generated['created_at'] = p['created_at']
            if p.get('retrieved_materials'):
                generated['retrieved_materials'] = p['retrieved_materials']
            if p.get('revision_instruction'):
                generated = await revise_project(generated, p['revision_instruction'])
            return generated
        async def draw():
            if p['mode'] == 'demo':
                return await asyncio.to_thread(render_demo_images, p, project_dir(pid))
            return await ModelClient().images(p, project_dir(pid), lambda msg: job_log(job, msg))
        async def speak():
            return await generate_audio(p, project_dir(pid), lambda msg: job_log(job, msg))
        async def movie():
            await asyncio.to_thread(searcher.release_clip)
            job_log(job, '检索结果已保存；释放CLIP会话内存后编码视频。')
            result = await asyncio.to_thread(render_video, p, project_dir(pid), lambda msg: job_log(job, msg))
            await asyncio.to_thread(render_pdf, result, project_dir(pid))
            return result
        async def revision(instruction):
            return await revise_project(p, instruction)
        async def retrieve():
            found = await asyncio.to_thread(searcher.search, p['inputs'].get('interest','') + ' ' + THEMES[p['theme']]['label'])
            p['retrieved_materials'] = found.get('generation_suggestions', {})
            job_log(job, '检索工具已记录与本故事相关的素材建议。')
            return p
        async def review():
            normalize_story(p)
            p['review_result'] = {'valid_json': True, 'scene_count': len(p['scenes']), 'speaking_roles': sorted({d['character'] for s in p['scenes'] for d in s['dialogues']})}
            return p
        async def planner(instruction, current):
            response = await ModelClient(text_model='glm-4-flash-250414').chat_json([
                {'role':'system','content':'你是儿童故事创作Agent的流程规划器。仅返回JSON {"plan":[工具名],"summary":"简短执行说明"}。核心工具write_story/generate_images/generate_audio/render_video全部必须调用，核心依赖顺序必须为write_story→generate_images→generate_audio→render_video。可自主选择是否在适当位置加入retrieve_materials和review_story，review_story只读检查结构而不修改正文，可在写作后插入；重写或实际修改时须重新生成依赖媒体。最多12步，不能使用其他工具。'},
                {'role':'user','content':json.dumps({'instruction': instruction, 'title':current['title'], 'theme':current['theme'], 'scenes':len(current['scenes']), 'goal':'生成适龄绘本、有声书和视频；检查结构和素材相关性'},ensure_ascii=False)}])
            job_log(job, '模型规划：' + str(response.get('summary',''))[:200])
            return response['plan']
        result = await run_agent(p, {'write_story':write,'generate_images':draw,'generate_audio':speak,'render_video':movie,'revise_story':revision,'retrieve_materials':retrieve,'review_story':review}, planner if p['mode']=='live' else None, job, save_project)
        trace = result.get('trace', [])
        write_json(project_dir(pid) / 'agent_trace.json', {k:v for k,v in result.items() if k!='project'})
        (project_dir(pid)/'agent_trace.md').write_text('# 故事创作流程日志\n\n模式：'+result.get('planning_mode','')+'\n\n'+'\n'.join(f'- {x.get("time","")} {x.get("message","")}' for x in trace),encoding='utf-8')
        p['agent_completed'] = True
        p['agent_job_id'] = job['id']
        p['agent_manifest_url'] = f'/files/projects/{pid}/agent-final-manifest.json'
        p['agent_planning_mode'] = result.get('planning_mode')
        save_project(p)
        await asyncio.to_thread(write_manifest, p, project_dir(pid), job['id'])
        return {k:v for k,v in result.items() if k not in {'project','trace'}} | {'message':'四个创作工具已实际执行，完整日志已保存。'}
    return launch_job(pid, '故事创作Agent', work, instruction=req.instruction, pending_instruction=req.instruction, pause_after_story=req.pause_after_story)

@app.get('/api/jobs/{jid}')
async def get_job(jid: str):
    if jid not in JOBS:
        raise HTTPException(404, '没有找到该任务。')
    return JOBS[jid]

@app.post('/api/jobs/{jid}/intervene')
async def intervene(jid: str, req: Instruction):
    job = await get_job(jid)
    if job['status'] not in {'running','paused','queued'} or job['label'] != '故事创作Agent':
        raise ValueError('只能介入正在运行或暂停的Agent任务。')
    job['pending_instruction'] = req.instruction
    job_log(job, '已收到用户修改指令，将在下一工具执行前处理。')
    persist_job(job)
    return {'ok': True}

@app.post('/api/jobs/{jid}/resume')
async def resume(jid: str):
    job = await get_job(jid)
    if job['status'] != 'paused':
        raise ValueError('任务当前没有暂停。')
    job['resume_requested'] = True
    return {'ok': True}

@app.get('/api/projects/{pid}/book.pdf')
async def book(pid: str):
    ensure_idle(pid)
    BUSY.add(pid)
    try:
        p = load_project(pid)
        existing = project_dir(pid) / str(p.get('pdf_url','')).rsplit('/',1)[-1]
        path = existing if p.get('pdf_url') and existing.is_file() else await asyncio.to_thread(render_pdf, p, project_dir(pid))
        save_project(p)
        return FileResponse(path, media_type='application/pdf', filename=f'{p["title"]}.pdf')
    finally:
        BUSY.discard(pid)

@app.get('/api/projects/{pid}/export.zip')
async def export(pid: str):
    ensure_idle(pid)
    p = load_project(pid)
    buffer = io.BytesIO()
    folder = project_dir(pid)
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in folder.rglob('*'):
            if path.is_file() and not path.is_symlink() and not any(x.startswith('.') or x in {'video_work','audio_parts'} for x in path.relative_to(folder).parts) and path.stat().st_size > 0 and path.suffix in {'.json','.md','.png','.jpg','.mp3','.mp4','.pdf','.wav','.srt'}:
                archive.write(path, path.relative_to(folder).as_posix())
    return Response(buffer.getvalue(), media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="storybook-{pid}.zip"'})

@app.get('/api/assets')
async def assets(q: str='', type: str='all'):
    if len(q)>500:
        raise ValueError('查询过长，请缩短到500字以内。')
    return await asyncio.to_thread(searcher.search, q, type, 24)

@app.post('/api/prompt-compare')
async def compare(req: CompareRequest):
    async def work(job):
        p = load_project(req.project_id)
        mode = req.mode or p['mode']
        rows = []
        for i, strategy in enumerate(STRATEGIES):
            job_log(job, '运行Prompt对比：'+STRATEGIES[strategy])
            params = StoryInput.model_validate({**p['inputs'],'strategy':strategy,'mode':mode})
            if mode == 'live':
                comparison_client = ModelClient()
                messages = prompt_messages(params)
                story = normalize_story(await comparison_client.chat_json(messages))
            else:
                story, messages = demo_story(params), prompt_messages(params)
            row = {'strategy':strategy,'strategy_label':STRATEGIES[strategy],'source':'actual_api' if mode=='live' else 'demo_template',
                   'model':comparison_client.last_model if mode=='live' else None,'processing':story.get('processing',{}),
                   'json_valid':True,'characters':len(story['characters']),'scenes':len(story['scenes']),
                   'tts_characters':sum(len(d['text']) for s in story['scenes'] for d in s['dialogues']),
                   'example':story['scenes'][0]['text'],'messages':messages,'story':story,
                   'length_target_met':sum(len(d['text']) for s in story['scenes'] for d in s['dialogues']) >= {'short':1000,'medium':1400,'long':1900}[params.length],
                   'quality_rating':'待本人按连贯性、适龄性、创意、可配图性人工评分'}
            rows.append(row)
            job['progress'] = int((i+1)/3*95)
        report = {'mode':mode,'comparisons':rows,'note':'本地模板示例不构成真实模型Prompt效果比较；人工评分不可由示例伪造。' if mode=='demo' else '三种策略均以相同输入实际调用；保留长度差异，不为比较结果强行扩写或压缩。质量分请本人阅读后填写。'}
        write_json(project_dir(p['id'])/'prompt-comparison.json',report)
        content = '# Prompt策略对比报告\n\n'+report['note']+'\n\n|策略|来源|JSON可解析|角色数|场景数|配音字数|人工评分|\n|---|---|---|---|---|---|---|\n'
        content += '\n'.join(f'|{r["strategy_label"]}|{r["source"]}|是|{r["characters"]}|{r["scenes"]}|{r["tts_characters"]}|待本人填写|' for r in rows)
        for row in rows:
            content += '\n\n## '+row['strategy_label']+'\n\n生成示例：\n\n'+row['example']+'\n'
        (project_dir(p['id'])/'prompt-comparison.md').write_text(content,encoding='utf-8')
        p['prompt_comparison_mode']=mode
        save_project(p)
        return {'message':report['note'],'comparisons':[{k:v for k,v in r.items() if k not in {'story','messages'}} for r in rows]}
    return launch_job(req.project_id,'三种Prompt策略对比',work)

@app.get('/api/course')
async def course():
    projects = list_projects()
    counts = searcher.counts
    live_story = any(p['mode']=='live' for p in projects)
    live_images = any(p['scenes'] and all(s.get('image_source')=='image_api' and s.get('image_url') for s in p['scenes']) for p in projects)
    audio_ok = any(p.get('audio_proof',{}).get('duration',0)>=180 and len(p.get('audio_proof',{}).get('voices',[]))>=3 for p in projects)
    video_ok = any(p.get('video_proof',{}).get('duration',0)>=60 for p in projects)
    compare_ok = any(p.get('prompt_comparison_mode')=='live' for p in projects)
    agents = sum(bool(p.get('agent_completed')) and p.get('agent_planning_mode') == 'model' and verify_manifest(p, project_dir(p['id'])) for p in projects)
    demo_agents = sum(bool(p.get('agent_completed')) and p.get('agent_planning_mode') == 'demo_rules' for p in projects)
    clip = await asyncio.to_thread(lambda:searcher.clip_ready)
    checks=[
        {'label':'三种故事主题','passed':True,'detail':'森林、太空、海洋均可创作和阅读。'},
        {'label':'Python真实模型调用与Prompt对比','passed':live_story and compare_ok,'detail':'需配置密钥并实际生成故事、运行三策略对比；模板示例不计入。'},
        {'label':'逐幕文生图API产物','passed':live_images,'detail':'需全书逐幕通过文生图API生成；角色外貌一致性仍需本人核查。'},
        {'label':'三音色、三分钟有声书','passed':audio_ok,'detail':'按真实配音证明中的音色数量和解码音频时长检查。'},
        {'label':'带字幕和音乐的视频','passed':video_ok,'detail':'按真实视频产物时长检查，至少60秒。'},
        {'label':'素材数量和CLIP检索','passed':counts.get('templates',0)>=10 and counts.get('images',0)>=20 and counts.get('sounds',0)>=5 and clip,'detail':f'{counts}；CLIP就绪：{clip}。'},
        {'label':'两个Agent案例与最终产物对应','passed':agents>=2,'detail':f'最终产物哈希验证通过的模型案例{agents}个；本地规则演示案例{demo_agents}个。旧任务成功但无最终产物绑定时不计入此项。'},
    ]
    titles=['个性化故事网页','结构化故事与Prompt工程','角色一致性绘本','多角色有声书','故事视频合成','多模态素材检索','交互式故事Agent','现场展示与答辩']
    done=[True,live_story and compare_ok,live_images,audio_ok,video_ok,checks[5]['passed'],agents>=2,False]
    details=[['三主题、友好交互；需本人完成Trae操作记录与2分钟演示视频。'],['直接调用模型API；比较三策略并保留输出。'],['每幕至少1图；已固定详细外貌；当前免费接口缺少Seed，严格方案仍待补齐。'],['至少3个不同音色，音频不少于180秒。'],['MP4不少于60秒，有画面、配音、音乐和同步字幕。'],['至少10模板、20图片、5音效；三个查询评估。'],['至少4工具；支持中途干预；两个完整案例和架构日志。'],['现场运行；8—10分钟；至少3种关联模态；本人讲解和答辩。']]
    return {'scope':'technical_artifacts_only','notice':'仅检查技术条件与产物，不代表教师作业验收。','checks':checks,'weeks':[{'week':i+1,'title':title,'status':'completed' if done[i] else 'pending','details':details[i]} for i,title in enumerate(titles)]}

PROJECTS.mkdir(parents=True,exist_ok=True)
(DATA/'library').mkdir(parents=True,exist_ok=True)
app.mount('/files/projects',StaticFiles(directory=PROJECTS),name='project-files')
app.mount('/files/library',StaticFiles(directory=DATA/'library'),name='library-files')
app.mount('/',StaticFiles(directory=ROOT/'web',html=True),name='web')
