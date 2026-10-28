"""Original demonstration stories and the three reproducible prompt strategies."""
import re
import copy
from .models import StoryInput, StoryOutput
from .storage import now, new_id

THEMES = {
 'forest': {'label': '森林探险', 'place': '萤火森林', 'goal': '让迷路的星星回到天空', 'object': '一颗落在蘑菇旁的小星星', 'friend': '萤火虫', 'mentor': '老猫头鹰', 'vehicle': '树叶小船', 'obstacle': '被雨水冲断的小木桥', 'gift': '星光种子', 'sky': '树叶间漏下的月光', 'end': '森林里的每一盏萤火灯都亮了'},
 'space': {'label': '太空旅行', 'place': '棉花糖星系', 'goal': '为熄灭的星球找回光芒', 'object': '一颗不再发光的导航星', 'friend': '小机器人', 'mentor': '星际向导', 'vehicle': '蒲公英飞船', 'obstacle': '不断改变方向的陨石带', 'gift': '星光电池', 'sky': '一层层浅紫色的星云', 'end': '小小星球重新挂上了明亮的光环'},
 'ocean': {'label': '海洋奇遇', 'place': '珊瑚海湾', 'goal': '为海底灯塔找回温暖的光', 'object': '一枚光芒微弱的月亮贝壳', 'friend': '小海龟', 'mentor': '老鲸鱼', 'vehicle': '透明泡泡船', 'obstacle': '把路标吹乱的回旋海流', 'gift': '发光珍珠', 'sky': '穿过海面的金色波纹', 'end': '海底灯塔把回家的路照得亮亮的'},
}

FOX = '暖橘色幼年小狐狸，奶油白脸颊和尾尖，大而有神的暖棕色眼睛，琥珀色虹膜与两点柔和高光，青绿色围巾，金黄色小背包。保持同样的脸、耳朵、围巾和背包，不改变角色物种。'
STYLE = '高品质低龄儿童绘本水粉水彩插画，柔和纸张纹理，奶油白与杏橘色、鼠尾草绿配色。主角是超级可爱Q版幼年小狐狸：大圆头占全身近一半、圆鼓鼓脸颊、圆润杏仁形大眼睛，暖棕与琥珀色虹膜有层次，两点柔和高光，目光好奇亲切，短圆口鼻、淡桃色腮红、短胖身体与短短四肢、蓬松圆尾、亲切微笑，避免点状豆豆眼；绿色小围巾与金黄色小背包固定不变。圆润幼态、轻盈童话感、柔光、简洁精致构图，所有角色完整入画，适合4到7岁儿童，不添加文字，保留平台要求的AI生成标识。'
STRATEGIES = {'zero_shot': '零样本：直接规定目标与输出结构', 'few_shot': '少样本：提供一段结构示例', 'role_play': '角色扮演：儿童文学作家与分镜设计师'}

def normalize_story(data: dict):
    if isinstance(data, dict) and isinstance(data.get('characters'), list):
        data = {**data, 'characters':[dict(c) if isinstance(c,dict) else c for c in data['characters']]}
        for char in data['characters']:
            if isinstance(char,dict) and char.get('name') in {'旁白','叙述者','narrator'}:
                char.setdefault('traits','温柔耐心的故事讲述者')
                char.setdefault('appearance','画外音，无可见形象')
                char.setdefault('role','narrator')
    clean = StoryOutput.model_validate(data).model_dump()
    for i, char in enumerate(clean['characters']):
        char['id'] = char.get('id') or f'character_{i+1}'
    valid_names = {c['name'] for c in clean['characters']} | {'旁白'}
    for i, scene in enumerate(clean['scenes'], 1):
        scene['scene_id'] = i
        scene['title'] = (scene.get('title') or f'第{i}幕').strip('\"\'“”')
        for line in scene['dialogues']:
            if line['character'] not in valid_names:
                raise ValueError(f'配音角色“{line["character"]}”未出现在角色表。')
    # Recover only explicitly attributed quotations, never guess a speaker.
    attributed = 0
    names = sorted((n for n in valid_names if n not in {'旁白','叙述者','narrator'}), key=len, reverse=True)
    if names:
        pattern = re.compile(r'[“‘]([^”’]+)[”’]([，,。]?(' + '|'.join(re.escape(n) for n in names) + r')(?:说道|说|回答道|回答|问道|问)[。！!？?]?)')
        for scene in clean['scenes']:
            lines = []
            for row in scene['dialogues']:
                if row['character'] not in {'旁白','叙述者','narrator'}:
                    lines.append(row); continue
                cursor = 0
                for match in pattern.finditer(row['text']):
                    prefix = row['text'][cursor:match.start()]
                    if prefix.strip(): lines.append({**row,'text':prefix})
                    lines.append({**row,'character':match.group(3),'text':match.group(1)})
                    cursor = match.end(); attributed += 1
                if cursor:
                    if row['text'][cursor:].strip(): lines.append({**row,'text':row['text'][cursor:]})
                else: lines.append(row)
            scene['dialogues'] = lines
    for scene in clean['scenes']:
        scene['text'] = '\n'.join(d['text'] if d['character'] in {'旁白','叙述者','narrator'} else d['character']+'：'+d['text'] for d in scene['dialogues'])
    clean['processing']['text_synchronized_from_dialogues'] = True
    if attributed:
        clean['processing']['attributed_quotes_reassigned'] = attributed
        clean['processing']['attribution_note'] = '仅将原文中带有明确角色姓名和说话标记的引语分配给该角色，未新增台词。'
    return clean

def _whole_sentences(text: str) -> list[str]:
    parts=[];current='';quotes=0
    for char in text:
        current+=char
        if char=='“':quotes+=1
        elif char=='”':quotes=max(0,quotes-1)
        if quotes==0 and (char in '。！？!?' or (char=='”' and len(current)>1 and current[-2] in '。！？!?')):
            parts.append(current);current=''
    if current:parts.append(current)
    return parts

def compact_story(story: dict, target: int) -> dict:
    """Extract whole original sentences from overlong speech; never pad or invent."""
    result=copy.deepcopy(story)
    original=sum(len(d['text']) for s in result['scenes'] for d in s['dialogues'])
    if original <= target * 1.45:
        return result
    scene_budget=max(180,target//len(result['scenes']))
    for scene in result['scenes']:
        total=sum(len(d['text']) for d in scene['dialogues']) or 1
        reference=scene.get('title','')+scene.get('description','')
        keywords={reference[i:i+2] for i in range(max(0,len(reference)-1))}
        for row in scene['dialogues']:
            text=row['text']
            budget=max(45,round(scene_budget*len(text)/total))
            sentences=_whole_sentences(text)
            if len(sentences)<2 or len(text)<=budget:
                continue
            selected={0};used=len(sentences[0])
            order=[len(sentences)-1]+sorted(range(1,len(sentences)-1),key=lambda i:sum(k in sentences[i] for k in keywords)/(max(1,len(sentences[i]))**.5),reverse=True)
            for index in order:
                if used+len(sentences[index]) <= budget*1.12:
                    selected.add(index);used+=len(sentences[index])
            row['text']=''.join(sentences[i] for i in sorted(selected))
        scene['text']='\n'.join(d['text'] if d['character']=='旁白' else d['character']+'：'+d['text'] for d in scene['dialogues'])
    actual=sum(len(d['text']) for scene in result['scenes'] for d in scene['dialogues'])
    result['processing']={'method':'extractive_whole_sentences','original_tts_characters':original,'final_tts_characters':actual,'target_characters':target,'note':'仅抽取原始模型完整句子；未新增故事文字，原始响应另存。需本人核查衔接。'}
    return result

def make_project(story: dict, params: StoryInput, pid=None):
    return {**normalize_story(story), 'id': pid or new_id(), 'theme': params.theme,
            'created_at': now(), 'mode': params.mode,
            'provider': '本地模板与程序插画示例' if params.mode == 'demo' else '智谱API',
            'inputs': params.model_dump(), 'status': 'story_ready', 'cover_url': '', 'audio_url': '', 'video_url': '', 'pdf_url': ''}

def demo_story(params: StoryInput):
    n, t = params.name, THEMES[params.theme]
    place = params.setting.strip() or t['place']
    titles = ['口袋里的小小愿望', '和新朋友一起出发', '先停下来听一听', '每一种小本领都有光', '把勇气分享出去', '带着星光回家']
    narration = [
        f'在{place}的清晨，{n}把青绿色围巾仔细系好，又检查了一遍金黄色小背包。今天是{n}{params.age}岁后第一次自己出门探索。背包里装着水、一块小饼干，还有一本空白的发现手册。{n}最喜欢{params.interest or "观察世界、结交朋友"}，一直想把路上的新发现画下来。就在门口的小路边，{n}发现了{t["object"]}。它轻轻闪了两下，像是在努力说一句话。{n}蹲下身，没有急着把它带走，而是先安静地等了等。',
        f'绕过一片柔软的草地，{n}遇见了{t["friend"]}米粒。米粒正在整理一张画得歪歪扭扭的地图，脸上却带着认真又明亮的笑容。听完小小的愿望，米粒愿意一起{t["goal"]}。两个新朋友把地图铺开，用不同颜色标出已经知道的路和还不确定的地方。他们没有比赛谁走得更快，而是约好每到一个路口就互相等一等。{t["vehicle"]}载着他们慢慢前进，{t["sky"]}落在地图上，像一串温柔的提示。',
        f'旅程走到一半，前面出现了{t["obstacle"]}。原来熟悉的方向一下子变得陌生，连米粒手里的地图也帮不上忙。{n}的耳朵垂了下来，握着背包带的手有一点点紧。远处看起来很安静，可是越着急，细小的声音就越听不清。两个朋友把船停在安全的地方，先喝了一点水，再一起数了五次呼吸。慢慢地，{n}听见了不同方向传来的回声，也发现有一排小小的记号没有被打乱。',
        f'沿着记号，他们找到了{t["mentor"]}星爷爷。星爷爷没有马上告诉他们答案，而是请他们说说自己已经观察到的线索。{n}想起发现手册上记下的图案，米粒则想起旅途中光线改变的方向。他们把两张小纸并排放好，突然发现原来看似零散的线索能够拼成一条路。有人擅长仔细观察，有人擅长记住方向；只要愿意听完对方的话，小本领也能连成大办法。星爷爷把一枚{t["gift"]}交给他们，让他们自己试一试。',
        f'新的道路依然需要耐心。{n}负责观察路边的变化，米粒负责确认地图，每完成一小段就交换一次发现。最难的转弯处，{n}又有一点害怕，却把这种感觉诚实地说了出来。米粒没有笑，也没有催，只是伸出手陪着{n}一步一步往前。就在他们共同找到最后一个记号时，背包里的{t["gift"]}亮了起来。那光并不刺眼，却照见了朋友们脸上的笑容。原来勇敢并不需要一个人把所有事情都做完。',
        f'傍晚，他们终于完成了愿望，{t["end"]}。回家的路上，{n}没有把功劳都写给自己，而是在发现手册上画下米粒、星爷爷和一路帮助过他们的朋友。金黄色小背包里多了一张新的地图，上面留着一块空白，等着下一次探索。{n}把今天最重要的发现写在最后一页：遇到困难，可以先停一停、认真观察、说出需要，再和朋友一起试试。夜风轻轻吹过青绿色围巾，明天的故事还会继续。',
    ]
    speech = [
        (f'我还不知道你需要什么。不过没关系，我可以先听听。希望今天能找到帮助你的办法。', '我也愿意帮忙。我们先把知道的事情记下来，一点一点找答案。'),
        ('我有时候走得慢，因为我想看清每一件小事情。你会愿意等等我吗？', '当然愿意！认真观察也是很棒的本领。我认识方向，我们正好可以互相帮忙。'),
        ('我有一点害怕，也不知道该走哪边。我们能不能先休息一下，再做决定？', '可以呀。害怕的时候也可以开口。你听，那边的回声好像和刚才不一样。'),
        ('原来我的小小发现真的有用！我想先试着把这些线索连起来。', '我来看看地图。我们把你的观察和我的方向放在一起，就有两份力量啦。'),
        ('谢谢你等我。我想再试一次，这次我们一起走，可以吗？', '当然可以。前面那一小段我陪着你，后面你也可以带着我。'),
        ('今天我学会了，勇敢也可以是说出害怕、认真求助，然后和朋友继续前进。', '我也有新发现！朋友不是一直比谁更厉害，而是愿意把自己的小本领分享给对方。'),
    ]
    scenes = []
    for i, (text, (a, b)) in enumerate(zip(narration, speech), 1):
        dialogues = [{'character': '旁白', 'text': text, 'emotion': '温柔'},
                     {'character': n, 'text': a, 'emotion': '低语' if i == 3 else '兴奋' if i in {1, 6} else '温柔'},
                     {'character': '米粒', 'text': b, 'emotion': '兴奋' if i in {2, 5} else '温柔'}]
        if i == 4:
            dialogues.append({'character': '星爷爷', 'text': '不急着找一个最大的本领。把每个人愿意分享的小本领放在一起，路就会慢慢清楚起来。', 'emotion': '温柔'})
        scenes.append({'scene_id': i, 'title': titles[i-1], 'description': f'{place}，{titles[i-1]}，{t["sky"]}',
                       'text': text + '\n' + '\n'.join(f'{x["character"]}说：“{x["text"]}”' for x in dialogues[1:]),
                       'mood': ['好奇', '期待', '紧张', '思考', '勇敢', '温暖'][i-1],
                       'visual_prompt': f'{STYLE} 主角{n}：{FOX} 在{place}，{titles[i-1]}。伙伴是{t["friend"]}，故事目标是{t["goal"]}。', 'dialogues': dialogues})
    if params.length == 'short':
        for scene in scenes:
            scene['dialogues'][0]['text'] = scene['dialogues'][0]['text'][:110] + '。'
            scene['text'] = '\n'.join(x['text'] for x in scene['dialogues'])
    return {'title': f'{n}与{t["gift"]}的秘密', 'characters': [
        {'id': 'narrator', 'name': '旁白', 'traits': '温柔耐心，帮助小读者理解情节', 'appearance': '画外音', 'role': 'narrator'},
        {'id': 'hero', 'name': n, 'traits': '好奇、善良，学着表达害怕并寻求帮助', 'appearance': FOX, 'role': 'hero'},
        {'id': 'friend', 'name': '米粒', 'traits': '热情、耐心，擅长辨认方向', 'appearance': f'友好的{t["friend"]}，圆润轮廓，青绿色小挎包', 'role': 'friend'},
        {'id': 'mentor', 'name': '星爷爷', 'traits': '睿智、温和，鼓励孩子自己发现答案', 'appearance': f'慈祥的{t["mentor"]}，暖金色小眼镜', 'role': 'mentor'},
    ], 'scenes': scenes, 'moral': '勇敢可以从承认害怕开始；认真观察、表达需要、互相帮助，每一种小本领都会发光。'}

def prompt_messages(params: StoryInput, retrieval_context=''):
    base = ('你是儿童故事创作者。只输出合法JSON对象，不要Markdown或解释。内容安全、温暖、适龄，避免暴力、恐吓和隐私信息。'
            '输出字段：title, characters:[{name,traits,appearance,role}], scenes:[{scene_id,title,description,text,mood,visual_prompt,dialogues:[{character,text,emotion}]}], moral。'
            '除旁白外至少3位故事人物：小狐狸主角、小伙伴、可信赖的成年向导；三位人物都必须有独立对白，向导至少在2幕中直接发言。旁白单列，所有对白角色都在角色表。6个场景，scene_id从1连续递增。text应是这一幕完整故事，dialogues是同一故事的配音分段，不能遗漏剧情。'
            '每幕至少旁白、主角、伙伴说话。visual_prompt包含每个出场角色完整固定外貌和同一水粉童书风格，避免角色变脸。主角外观：' + FOX)
    if params.strategy == 'role_play':
        base = '你同时担任儿童文学作家和绘本分镜设计师，擅长用对话、具体行动和完整起承转合讲故事。' + base
    elif params.strategy == 'few_shot':
        base += ('结构片段示例：{"title":"小狐狸的第一盏灯","characters":[{"name":"小栗","traits":"好奇","appearance":"橘色狐狸、青绿围巾","role":"hero"}],'
                 '"scenes":[{"scene_id":1,"title":"发现","description":"晨光中的树林","text":"小栗发现了一盏灯。",'
                 '"mood":"好奇","visual_prompt":"水粉童书，橘色狐狸戴青绿围巾，在晨光树林看一盏灯",'
                 '"dialogues":[{"character":"小栗","text":"是谁把灯忘在这里了？","emotion":"好奇"}]}],"moral":"学会观察"}。这只是格式片段，实际输出须符合6场景和至少3角色要求。')
    target = {'short': '1000', 'medium': '1400', 'long': '1900'}[params.length]
    narrator_min, dialogue_min = {'short':(90,35), 'medium':(130,50), 'long':(180,70)}[params.length]
    user = (f'为目标受众{params.audience_age}岁儿童创作一个完整中文故事。主角名字：{params.name}；主角年龄：{params.age}岁（与读者年龄独立）；兴趣：{params.interest}；'
            f'主题：{THEMES[params.theme]["label"]}；地点：{params.setting or THEMES[params.theme]["place"]}；'
            f'必须认真满足长度：全部dialogues[].text合计至少{target}个汉字。每一幕的dialogues包含一段至少{narrator_min}汉字的旁白，再让主角与伙伴各说至少{dialogue_min}汉字；用具体动作、环境细节和对话扩展剧情，不要用几句短对白代替整幕故事。6幕的配音内容必须完整，场景text与dialogues讲述同一情节。长故事配音目标超过3分钟。情绪可用温柔/兴奋/悲伤/低语。'
            f'主角必须保持给定小狐狸外观。按目标受众年龄选择词汇与句长，主角年龄应在故事行动和人物设定中体现。情节包含发现、困难、合作、解决和反思。旁白只叙述动作，不把角色的直接引语放进旁白；所有直接发言分配给真正说话的角色。首次出场应交代身份，关键困难必须写出解决过程；不让儿童独自冒险、硬闯尖刺或搬动重物，遇险先停止并请可信成人帮助。\n可选素材参考：{retrieval_context[:2500]}')
    return [{'role': 'system', 'content': base}, {'role': 'user', 'content': user}]

def revise_demo(project: dict, instruction: str):
    values = dict(project['inputs'])
    theme = next((code for word, code in [('海洋','ocean'),('海底','ocean'),('太空','space'),('星球','space'),('森林','forest')] if word in instruction), None)
    if theme:
        values['theme'] = theme
        values['setting'] = ''
    match = re.search(r'(?:名字|主角)(?:叫|改成|改为|换成|换为|是)\s*[“"\']?([\u4e00-\u9fffA-Za-z]{1,12})', instruction)
    if match and match.group(1) not in {'女孩','男孩','小女孩','小男孩'}:
        values['name'] = match.group(1).split('，')[0]
    gender = '女孩子' if '女孩' in instruction else '男孩子' if '男孩' in instruction else ''
    values['mode'] = 'demo'
    params = StoryInput.model_validate(values)
    revised = make_project(demo_story(params), params, project['id'])
    if gender:
        revised['characters'][1]['traits'] += f'；主角是一位{gender}'
    revised['created_at'] = project['created_at']
    revised['revision_instruction'] = instruction
    revised['revision_note'] = '本地示例支持改名、三主题切换和性别标注；复杂情节修改请使用真实模型。'
    return revised
