"""Create the offline, clearly labelled storybook demonstration asset library.

No API, paid model, downloaded illustration or external audio is used here.
Run with the bundled Python and the project's optional dependency directory.
"""
from __future__ import annotations

import json
import math
import sys
import wave
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from storybook.media import draw_demo_illustration

LIBRARY=ROOT/"data"/"library"
THEMES={"forest":"森林探险","space":"太空旅行","ocean":"海洋奇遇"}
SCENE_TITLES={
    "forest":["晨光中的小木屋","苔藓桥上的约定","蘑菇邮局的来信","会发光的勇气","风铃树下的朋友","口袋里的种子","雨后的小小发现","把星光送回家"],
    "space":["装满好奇的火箭","月亮上的第一枚脚印","星星修理铺","机器人也会想家","环形星球的拥抱","银河信使","寻找温柔的光","我们共享一片星空"],
    "ocean":["穿过蓝色的光","珊瑚花园的秘密","海龟米粒的地图","贝壳里的小愿望","水母灯下的舞会","勇敢的小小信使","潮汐带来的礼物","一起守护蓝色家园"],
}

STORY_SEEDS=[
    ("forest","会发光的种子","小栗和萤火虫米粒寻找一粒会发光的种子，发现它只在被认真照顾时亮起。","耐心照顾小生命，比急着看见结果更重要。",["自然","耐心","种子","成长"]),
    ("forest","蘑菇邮局的一封信","一封被雨打湿的信没有写地址。小栗跟着森林里的声音，替它找到等待的朋友。","认真倾听，能找到被忽略的需要。",["友谊","倾听","助人","邮局"]),
    ("forest","胆小的风也要出发","小栗不敢独自穿过苔藓桥，米粒陪他把大困难拆成一步一步的小目标。","勇敢可以很小，也可以和朋友一起练习。",["勇气","情绪","桥","合作"]),
    ("forest","把星光送回家","森林停电了，小栗召集朋友，用自己的微光为迷路的猫头鹰照亮回家的路。","每个人的一点点力量，都能照亮别人。",["合作","分享","星光","归家"]),
    ("space","月亮忘记了晚安","月亮没有收到地球的晚安信，小栗和机器人米粒乘纸火箭，修好一条失灵的星际邮路。","表达关心，让遥远的朋友也感到温暖。",["月亮","表达","火箭","友谊"]),
    ("space","星星修理铺","小栗发现一颗忽明忽暗的星星。它并没有坏，只是需要有人听完它的小烦恼。","难过时，可以说出来，也可以被认真倾听。",["星星","情绪","倾听","同理心"]),
    ("space","机器人米粒的新朋友","米粒误把陨石当成礼物，小栗和星际向导一起认识不同星球的生活习惯。","不同的想法，也值得被理解和尊重。",["机器人","尊重","差异","科学"]),
    ("space","一口袋银河尘","为了给家人带回一条银河，小栗收集星尘，却发现最好的纪念是一起经历的故事。","珍贵的记忆，来自陪伴和经历。",["银河","亲情","陪伴","探索"]),
    ("ocean","会唱歌的贝壳","小栗和海龟米粒寻找贝壳歌声的来源，发现是老鲸鱼在给海洋的新生命唱摇篮曲。","安静地观察，会听见世界细小的美好。",["贝壳","鲸鱼","声音","观察"]),
    ("ocean","珊瑚花园的颜色","珊瑚花园失去了颜色，小栗和海洋朋友从捡起一小片垃圾开始，一起让家园恢复生机。","保护环境，可以从身边的一件小事开始。",["珊瑚","环保","家园","合作"]),
    ("ocean","海龟的慢慢地图","小栗嫌米粒游得太慢，但米粒仔细记下每一处海流，带大家平安穿过迷雾海湾。","每个人都有自己的节奏和长处。",["海龟","节奏","尊重","耐心"]),
    ("ocean","送给潮汐的小礼物","小栗想留下所有漂亮贝壳，后来学会只带走照片，把海边的小家还给寄居蟹。","喜欢一个地方，也可以选择轻轻地守护它。",["海边","分享","环保","寄居蟹"]),
]


def _save_wav(path: Path,samples,sample_rate=24000):
    import numpy as np
    path.parent.mkdir(parents=True,exist_ok=True)
    samples=np.asarray(samples,dtype=float)
    maximum=float(np.max(np.abs(samples)))
    if maximum>.85:samples=samples*(.85/maximum)
    encoded=np.int16(np.clip(samples,-1,1)*32767)
    with wave.open(str(path),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(sample_rate);f.writeframes(encoded.tobytes())


def _make_sounds():
    """Original musical notes and shaped natural textures; genuine playable PCM."""
    import numpy as np
    sr=24000;duration=16;t=np.arange(sr*duration)/sr
    rng=np.random.default_rng(20261025)
    sounds=[]
    scales={"forest":[261.63,329.63,392.00,523.25,440,392,329.63,293.66],"space":[220,277.18,329.63,440,415.30,329.63,277.18,246.94],"ocean":[293.66,369.99,440,587.33,493.88,440,369.99,329.63]}
    for theme,notes in scales.items():
        audio=np.zeros_like(t)
        # Soft bell melody on a quiet breathing pad. 8 notes × 2 seconds.
        for i,note in enumerate(notes):
            local=t-i*2
            env=np.where(local>=0,(1-np.exp(-np.maximum(local,0)*18))*np.exp(-np.maximum(local,0)/1.1),0)
            audio+=.12*env*(np.sin(2*np.pi*note*local)+.28*np.sin(2*np.pi*2*note*local)+.1*np.sin(2*np.pi*3*note*local))
        for freq in [notes[0]/2,notes[2]/2,notes[0]]:
            audio+=.025*np.sin(2*np.pi*freq*t)*(.7+.3*np.sin(2*np.pi*.12*t))
        fade=np.minimum(t/1,1)*np.minimum((duration-t)/1.5,1)
        path=LIBRARY/"sounds"/f"bgm-{theme}.wav";_save_wav(path,audio*fade)
        sounds.append({"id":f"bgm-{theme}","type":"sound","title":f"{THEMES[theme]} · 轻柔音乐","description":"16 秒可播放轻柔背景音乐，本地程序合成原创音符；适合循环与低音量混音。","tags":[THEMES[theme],"背景音乐","轻柔","BGM",theme],"theme":theme,"path":f"sounds/{path.name}","url":f"/files/library/sounds/{path.name}","duration":16,"source":"local_procedural_audio"})
    for name,title,theme,seconds in [("magic-chime","发现星光 · 风铃音效","space",4),("gentle-waves","蓝色海湾 · 柔和海浪","ocean",8),("forest-breeze","叶片轻响 · 森林微风","forest",8)]:
        st=np.arange(sr*seconds)/sr;audio=np.zeros_like(st)
        if name=="magic-chime":
            for k,freq in enumerate([523.25,659.25,783.99,1046.5]):
                local=st-k*.34;env=np.where(local>=0,(1-np.exp(-np.maximum(local,0)*50))*np.exp(-np.maximum(local,0)/.8),0)
                audio+=.13*env*(np.sin(2*np.pi*freq*local)+.2*np.sin(2*np.pi*2.01*freq*local))
        else:
            # Smoothed seeded noise with a slowly swelling envelope resembles
            # water and wind without an abrasive white-noise high-frequency edge.
            noise=rng.normal(0,1,len(st))
            smooth=np.convolve(noise,np.ones(22 if theme=="ocean" else 44)/(22 if theme=="ocean" else 44),mode="same")
            envelope=(.55+.45*np.sin(2*np.pi*(.23 if theme=="ocean" else .15)*st-.5))
            audio=.26*smooth*envelope
            if theme=="forest":
                for i in range(3):
                    local=st-(1.2+i*2.1)
                    env=np.exp(-((local)/.085)**2)
                    audio+=.045*env*np.sin(2*np.pi*(1300*st+200*st**2))
        audio*=np.minimum(st/.3,1)*np.minimum((seconds-st)/.5,1)
        path=LIBRARY/"sounds"/f"{name}.wav";_save_wav(path,audio)
        sounds.append({"id":name,"type":"sound","title":title,"description":f"{seconds} 秒真实可播放 WAV 音效，本地程序合成示例，可用于故事转场或氛围。","tags":[THEMES[theme],"音效","氛围",name],"theme":theme,"path":f"sounds/{path.name}","url":f"/files/library/sounds/{path.name}","duration":seconds,"source":"local_procedural_audio"})
    return sounds


def main():
    LIBRARY.mkdir(exist_ok=True,parents=True);assets=[];templates=[]
    for theme in THEMES:
        for index,title in enumerate(SCENE_TITLES[theme]):
            relative=f"images/{theme}-{index+1:02d}.png"
            draw_demo_illustration(theme,index,LIBRARY/relative,title)
            assets.append({"id":f"image-{theme}-{index+1:02d}","type":"image","title":title,"description":f"{THEMES[theme]}主题绘本插画。固定橘色小狐狸、青绿色围巾、金色背包，柔和配色和留白；本地 Pillow 程序绘制示例，非 AI 生成。","tags":[THEMES[theme],"小狐狸","绘本","柔和","儿童",theme,title],"theme":theme,"path":relative,"url":f"/files/library/{relative}","width":1200,"height":900,"source":"local_program_demo","alt":f"{title}，小狐狸在{THEMES[theme]}中和伙伴一起探索"})
            assets[-1]["en_description"]={"forest":"An orange fox wearing a teal scarf and a golden backpack explores a gentle green forest with a firefly, trees, mushrooms and a little cottage. Pastel children's storybook illustration.","space":"An orange fox wearing a teal scarf and a golden backpack explores the moon with a mint robot, rocket, planets and stars. Pastel children's storybook illustration.","ocean":"An orange fox wearing a teal scarf and a golden backpack explores a blue ocean with a sea turtle, coral, fish and shells. Pastel children's storybook illustration."}[theme]
            print(f"图片 {relative}",flush=True)
    for index,(theme,title,premise,moral,tags) in enumerate(STORY_SEEDS):
        tid=f"template-{theme}-{index%4+1:02d}"
        outline_titles=["口袋里的小愿望","和伙伴一起出发","一个意想不到的困难","停下来，认真想一想","一起试试新的办法","把发现带回家"]
        outline=[{"title":outline_titles[i],"text":f"{premise} 这是第 {i+1} 幕：{outline_titles[i]}。以小栗和米粒的行动、感受和对话推动情节，结尾回应“{moral}”。","visual_prompt":f"{THEMES[theme]}，{SCENE_TITLES[theme][i]}，小栗暖橘色狐狸、奶油白脸颊和尾尖、青绿色围巾、金色背包，儿童绘本水彩质感，留白构图。","mood":["好奇","期待","紧张","安静","勇敢","温暖"][i]} for i in range(6)]
        template={"id":tid,"type":"template","title":title,"description":premise,"premise":premise,"moral":moral,"tags":[THEMES[theme],*tags,"故事模板",theme],"theme":theme,"path":f"templates/{tid}.json","url":f"/files/library/templates/{tid}.json","age_range":"4–9 岁","scene_count":6,"outline":outline,"characters":[{"name":"小栗","role":"protagonist","appearance":"暖橘色小狐狸、奶油白脸颊和尾尖、青绿色围巾、金色小背包"},{"name":"米粒","role":"companion","appearance":{"forest":"一只温柔的小萤火虫","space":"有发光心形灯的薄荷绿机器人","ocean":"戴着海草小围巾的海龟"}[theme]}],"source":"local_story_template","cover_url":f"/files/library/images/{theme}-{index%4+1:02d}.png"}
        target=LIBRARY/template["path"];target.parent.mkdir(exist_ok=True,parents=True);target.write_text(json.dumps(template,ensure_ascii=False,indent=2),encoding="utf-8")
        templates.append(template);assets.append(template)
    assets.extend(_make_sounds())
    manifest={"version":1,"title":"星芽故事屋本地示例素材库","description":"24 张原创程序插画、12 个故事模板、6 个可播放 WAV 音频。示例插画为程序绘制，非 AI 生成。","license":"项目内程序原创示例素材，可用于本项目学习、演示与故事导出。","assets":assets,"templates":templates,"counts":{"templates":12,"images":24,"sounds":6}}
    (LIBRARY/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(manifest["counts"],ensure_ascii=False),flush=True)


if __name__=="__main__":
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    main()
