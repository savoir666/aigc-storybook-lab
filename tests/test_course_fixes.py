import json
import pytest
from pydantic import ValidationError
from storybook.models import StoryInput
from storybook.story import prompt_messages, demo_story, make_project
from storybook.retrieval import AssetSearch
from storybook.evidence import write_manifest, verify_manifest


def test_independent_ages_and_legacy_books():
    old = StoryInput.model_validate({'name':'小芽','age':8})
    assert old.audience_age == 8
    params = StoryInput(age=9, audience_age=5)
    prompt = prompt_messages(params)[1]['content']
    assert '目标受众5岁' in prompt and '主角年龄：9岁' in prompt
    assert make_project(demo_story(params),params,'test')['inputs']['audience_age'] == 5
    with pytest.raises(ValidationError):
        StoryInput(audience_age=99)


def test_character_and_outline_are_retrievable(tmp_path):
    library=tmp_path/'data/library';library.mkdir(parents=True)
    assets=[{'id':'one','type':'template','title':'故事一','characters':[{'name':'风铃鹿','traits':'爱收集银色羽毛'}],'outline':['寻找蓝莓钟楼']},
            {'id':'two','type':'template','title':'故事二','premise':'小鱼在海底种珊瑚'}]
    (library/'manifest.json').write_text(json.dumps({'assets':assets},ensure_ascii=False),encoding='utf-8')
    search=AssetSearch(tmp_path)
    assert search.search('风铃鹿银色羽毛','template',1)['results'][0]['id']=='one'
    assert search.search('蓝莓钟楼','template',1)['results'][0]['id']=='one'


def test_manifest_detects_post_agent_changes(tmp_path):
    p={'id':'test','inputs':{'age':6},'title':'故事','characters':[],'scenes':[],'moral':'合作'}
    (tmp_path/'agent_trace.json').write_text('{}',encoding='utf-8')
    write_manifest(p,tmp_path,'job')
    assert verify_manifest(p,tmp_path)
    p['title']='改后的故事'
    assert not verify_manifest(p,tmp_path)
    p['title']='故事'
    (tmp_path/'agent_trace.json').write_text('{"changed":true}',encoding='utf-8')
    assert not verify_manifest(p,tmp_path)


def test_ending_revision_preserves_previous_scenes(tmp_path,monkeypatch):
    import asyncio,copy
    from unittest.mock import AsyncMock
    from storybook import server
    params=StoryInput(mode='live')
    original=make_project(demo_story(params),params,'ending-test')
    scene=copy.deepcopy(original['scenes'][-1])
    scene['title']='大家一起完成的小心愿'
    scene['dialogues'].append({'character':'星爷爷','text':'你们都把自己的本领分享给朋友，这就是合作。以后遇到新的难题，也要这样先听听彼此的发现，再一起想办法。','emotion':'温柔'})
    scene['dialogues'][0]['text']+='他们把每个人的发现画进手册，又一起商量明天的分工。小栗收好水壶，米粒检查地图，两位朋友约好按时来看望种子，谁遇到困难就先停下来告诉对方。'
    client=type('Client',(),{'chat_json':AsyncMock(return_value={'scene':scene,'moral':'一起分享本领。'})})()
    monkeypatch.setattr(server,'ModelClient',lambda **kwargs:client)
    monkeypatch.setattr(server,'project_dir',lambda pid:tmp_path)
    monkeypatch.setattr(server,'save_project',lambda p:p)
    revised=asyncio.run(server.revise_project(original,'保留小栗，让结尾突出合作。'))
    assert revised['scenes'][:-1]==original['scenes'][:-1]
    assert revised['scenes'][-1]['title']=='大家一起完成的小心愿'
    assert revised['revision_method']=='model_ending_patch'
    assert client.chat_json.await_count==1


def test_audio_cache_rejects_changed_script_and_corrupt_media(tmp_path):
    import copy,hashlib
    from storybook.media import write_audio_cache,load_audio_cache
    params=StoryInput();p=make_project(demo_story(params),params,'cache-test')
    for i,scene in enumerate(p['scenes']):
        name=f'scene-{i+1:02}.mp3';(tmp_path/name).write_bytes(b'mock-scene-audio')
        scene.update(audio_url='/files/'+name,duration=1,segments=[])
    (tmp_path/'story-audio.mp3').write_bytes(b'mock-full-audio')
    p.update(audio_url='/files/story-audio.mp3',duration=6,segments=[],audio_proof={'real_tts':True,'voices':['one','two','three'],'sha256':hashlib.sha256(b'mock-full-audio').hexdigest()})
    write_audio_cache(p,tmp_path)
    same=copy.deepcopy(p);same.pop('audio_url')
    assert load_audio_cache(same,tmp_path) and same['audio_url']==p['audio_url']
    changed=copy.deepcopy(p);changed['scenes'][0]['dialogues'][0]['text']+='修改一句。'
    assert not load_audio_cache(changed,tmp_path)
    changed=copy.deepcopy(p);changed['scenes'][0]['dialogues'][0]['emotion']='悲伤'
    assert not load_audio_cache(changed,tmp_path)
    (tmp_path/'scene-02.mp3').write_bytes(b'corrupt')
    assert not load_audio_cache(copy.deepcopy(p),tmp_path)


def test_video_cache_rejects_visual_and_subtitle_changes(tmp_path,monkeypatch):
    import copy,hashlib
    from storybook import media
    library=tmp_path/'library';(library/'sounds').mkdir(parents=True);(library/'sounds/bgm-forest.wav').write_bytes(b'mock-bgm')
    monkeypatch.setattr(media,'LIBRARY',library)
    for name in ['scene.png','story-audio.mp3','story-video.mp4']:(tmp_path/name).write_bytes(b'mock-'+name.encode())
    prefix='/files/projects/'+tmp_path.name+'/'
    p={'theme':'forest','scenes':[{'image_url':prefix+'scene.png','title':'one','duration':60}], 'audio_url':prefix+'story-audio.mp3','segments':[{'start':0,'end':60,'text':'a'}],'video_url':prefix+'story-video.mp4','video_proof':{'sha256':hashlib.sha256((tmp_path/'story-video.mp4').read_bytes()).hexdigest()}}
    media.write_video_cache(p,tmp_path)
    assert media.load_video_cache(copy.deepcopy(p),tmp_path)
    changed=copy.deepcopy(p);changed['segments'][0]['text']='changed'
    assert not media.load_video_cache(changed,tmp_path)
    (tmp_path/'scene.png').write_bytes(b'changed pixels')
    assert not media.load_video_cache(copy.deepcopy(p),tmp_path)
