"""Local illustrated-book media, real Edge TTS, FFmpeg video and PDF exports.

The illustrations are explicitly deterministic, program-drawn demo assets. Edge
TTS and video exports never replace a failed voice request with synthetic silence.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import math
import os
import random
import re
import shutil
import subprocess
import textwrap
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "data" / "library"
VOICE_POOL = ("zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh-CN-XiaoyiNeural", "zh-CN-YunyangNeural")
SAMPLE_RATE = 24000
PALETTES = {
    "forest": {"top": "#e1efe0", "bottom": "#fcf3db", "ink": "#2b5747", "accent": "#e8aa66", "ground": "#b7d4aa"},
    "space": {"top": "#293b68", "bottom": "#8799b6", "ink": "#344563", "accent": "#e9c884", "ground": "#b7b6d1"},
    "ocean": {"top": "#bde9e7", "bottom": "#3a91aa", "ink": "#285e76", "accent": "#f2bd96", "ground": "#d9dbc0"},
}


def ffmpeg_path() -> str:
    """Return the actual bundled FFmpeg executable, or explain the dependency."""
    try:
        import imageio_ffmpeg
        executable = imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise RuntimeError("视频组件 imageio-ffmpeg 尚未安装，请先运行项目依赖安装。") from exc
    if not Path(executable).is_file():
        raise RuntimeError("未找到 FFmpeg 可执行文件，请重新安装 imageio-ffmpeg。")
    return executable


def _hex(value: str) -> tuple[int, int, int]:
    return tuple(int(value.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))


def _font(size: int, bold: bool = False):
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / ("msyhbd.ttc" if bold else "msyh.ttc"),
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "simhei.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _gradient(size: tuple[int, int], top: str, bottom: str, seed: int) -> Image.Image:
    import numpy as np
    w, h = size
    a, b = np.array(_hex(top)), np.array(_hex(bottom))
    line = np.linspace(0, 1, h)[:, None, None]
    arr = np.broadcast_to(a[None, None, :] * (1 - line) + b[None, None, :] * line, (h, w, 3)).copy()
    arr += np.random.default_rng(seed).normal(0, 0.75, (h, w, 1))
    return Image.fromarray(np.uint8(np.clip(arr, 0, 255)), "RGB")


def _hill(draw, w, y, amplitude, fill, phase=0.0):
    pts = [(0, 960)] + [(x, int(y + math.sin(x / 290 + phase) * amplitude)) for x in range(0, w + 32, 32)] + [(w, 960)]
    draw.polygon(pts, fill=fill)


def _cloud(d, x, y, scale, fill):
    for dx, dy, rx, ry in [(0, 0, 64, 24), (-38, -7, 34, 25), (12, -23, 39, 33), (45, -4, 39, 22)]:
        d.ellipse((x + (dx - rx) * scale, y + (dy - ry) * scale, x + (dx + rx) * scale, y + (dy + ry) * scale), fill=fill)


def _star(d, x, y, r, fill):
    d.polygon([(x, y-r), (x+r*.23, y-r*.23), (x+r, y), (x+r*.23, y+r*.23), (x, y+r), (x-r*.23, y+r*.23), (x-r, y), (x-r*.23, y-r*.23)], fill=fill)


def _fox(d, x, y, scale=1.0, space=False):
    """The same cream-cheeked orange fox, teal scarf and gold backpack always."""
    def box(coords):
        a,b,c,e = coords
        return x+a*scale, y+b*scale, x+c*scale, y+e*scale
    def poly(coords, fill):
        d.polygon([(x+a*scale, y+b*scale) for a,b in coords], fill=fill)
    orange, orange2, cream, teal, ink = "#d98b52", "#e9a265", "#fff2d4", "#4e918a", "#3a4d4e"
    # Tail and soft grounding shadow.
    d.ellipse(box((-88, 112, 118, 145)), fill="#567c7340" if d.mode == "RGBA" else "#779e89")
    poly([(-24, 72), (-97, 43), (-129, 69), (-105, 119), (-34, 119), (11, 94)], orange)
    poly([(-98, 45), (-130, 68), (-111, 108), (-83, 100), (-90, 70)], cream)
    # Backpack, feet and body.
    d.rounded_rectangle(box((-59, -1, -5, 83)), radius=int(16*scale), fill="#dbb15e", outline="#bb9250", width=max(1,int(3*scale)))
    d.ellipse(box((-45, 30, 56, 126)), fill=orange)
    d.ellipse(box((-29, 60, 37, 119)), fill=cream)
    d.ellipse(box((-37, 106, -2, 137)), fill="#ba714b")
    d.ellipse(box((20, 107, 58, 137)), fill="#ba714b")
    d.ellipse(box((43, 30, 69, 82)), fill=orange2)
    # The pointed ears are deliberately stable across all scenes.
    poly([(-54, -39), (-48, -105), (-3, -65)], orange)
    poly([(19, -67), (62, -101), (68, -31)], orange)
    poly([(-43,-53),(-42,-88),(-17,-64)], "#9d604d")
    poly([(33,-63),(56,-85),(59,-48)], "#9d604d")
    d.ellipse(box((-63, -78, 76, 28)), fill=orange2)
    poly([(-59,-23),(-15,-17),(8,14),(-25,22)], cream)
    poly([(72,-27),(35,-17),(8,14),(43,23)], cream)
    d.ellipse(box((-31,-36,-20,-23)), fill=ink)
    d.ellipse(box((34,-36,45,-23)), fill=ink)
    d.ellipse(box((-28,-35,-25,-31)), fill="#fff7e5")
    d.ellipse(box((37,-35,40,-31)), fill="#fff7e5")
    d.ellipse(box((-39,-17,-18,-6)), fill="#ecad87")
    d.ellipse(box((38,-17,59,-6)), fill="#ecad87")
    poly([(0,-8),(17,-8),(9,0)], ink)
    d.arc(box((-3,-3,20,11)), start=15, end=160, fill=ink, width=max(1,int(2*scale)))
    d.rounded_rectangle(box((-42, 15, 56, 33)), radius=int(8*scale), fill=teal)
    poly([(27,25),(57,22),(64,72),(46,65)], teal)
    if space:
        d.arc(box((-85,-120,100,57)), start=175, end=365, fill="#f2eedb", width=max(3,int(5*scale)))
        d.arc(box((-73,-110,90,47)), start=200, end=278, fill="#f8f4de", width=max(2,int(3*scale)))


def draw_demo_illustration(theme: str, index: int, destination: Path, title: str = "") -> Path:
    """Draw a 1200×900 original demo raster with consistent character design."""
    theme = theme if theme in PALETTES else "forest"
    palette = PALETTES[theme]
    w,h = 1280,960
    rng = random.Random(index * 7919 + {"forest":12,"space":25,"ocean":37}[theme])
    img = _gradient((w,h),palette["top"],palette["bottom"],index+13)
    # Drawing at working size then supersampling the graphic layer avoids jagged edges.
    layer = Image.new("RGBA",(w*2,h*2))
    d0 = ImageDraw.Draw(layer)
    class ScaledDraw:
        mode = "RGBA"
        def __getattr__(self,name):
            fn = getattr(d0,name)
            def scaled(coords,*args,**kwargs):
                if isinstance(coords,(list,tuple)) and coords and isinstance(coords[0],(list,tuple)):
                    coords=[tuple(int(v*2) for v in p) for p in coords]
                else:
                    coords=tuple(int(v*2) for v in coords)
                for k in ("width","radius"):
                    if k in kwargs: kwargs[k]=int(kwargs[k]*2)
                return fn(coords,*args,**kwargs)
            return scaled
    d=ScaledDraw()
    if theme == "forest":
        # Golden light and layered canopies create soft editorial depth.
        d.ellipse((870,78,1028,236),fill="#fff5cf")
        _cloud(d,360,175,1.35,"#f5f5dfb0")
        _cloud(d,1100,260,.8,"#fff6deb0")
        _hill(d,w,610,55,"#c3d9b6",.4)
        _hill(d,w,706,48,"#a5c698",1.3)
        _hill(d,w,826,40,"#8bb493",2.2)
        d.polygon([(480,960),(935,960),(793,756),(720,684),(678,691),(706,778)],fill="#ead7aa")
        for x,y,s in [(58,380,1.25),(232,350,.92),(1110,390,1.05),(1230,440,1.3)]:
            d.rounded_rectangle((x-14*s,y,x+14*s,800),radius=9,fill="#927c62")
            for dx,dy,r in [(-65,0,95),(35,-42,105),(78,38,89),(-13,-93,92)]:
                d.ellipse((x+(dx-r)*s,y+(dy-r)*s,x+(dx+r)*s,y+(dy+r)*s),fill=rng.choice(["#8db597","#77a68d","#b0c89b"]))
        for i in range(33):
            x,y=rng.randint(20,1260),rng.randint(785,930)
            d.line((x,y,x+3,y-20),fill="#628e7c",width=2)
            if i%3==0:
                for dx,dy in [(-4,0),(4,0),(0,-4),(0,4)]: d.ellipse((x+dx-4,y-24+dy-4,x+dx+4,y-24+dy+4),fill="#f6dfab")
                d.ellipse((x-3,y-27,x+3,y-21),fill="#d9ac63")
        # Different stories reveal a bridge, a cosy house, mushrooms or a lantern.
        if index%4==0:
            d.rounded_rectangle((885,604,1078,792),radius=30,fill="#efd8b3")
            d.polygon([(850,624),(976,510),(1103,625)],fill="#c18c6a")
            d.rounded_rectangle((950,690,1009,793),radius=28,fill="#a97a61")
            d.ellipse((911,648,945,685),fill="#fff1b6")
            d.ellipse((1011,648,1045,685),fill="#fff1b6")
        elif index%4==1:
            d.arc((766,640,1220,967),start=185,end=355,fill="#b98d61",width=24)
            d.arc((766,606,1220,925),start=185,end=355,fill="#ad815e",width=5)
            for x in range(810,1190,52): d.line((x,690,x,796),fill="#ad815e",width=5)
        else:
            for x,y,s in [(1038,822,1.1),(936,844,.7),(1138,805,.65)]:
                d.rounded_rectangle((x-12*s,y-45*s,x+13*s,y+5*s),radius=8,fill="#f5e6ca")
                d.pieslice((x-55*s,y-92*s,x+55*s,y-15*s),180,360,fill="#d99b7b")
                for dx in (-20,17):d.ellipse((x+dx*s-6,y-72*s,x+dx*s+6,y-60*s),fill="#f9e9c9")
        fx,fy = (566+index%3*44,701+index%2*16)
        _fox(d,fx,fy,1.28)
        # Companion firefly and its travelling dotted trail.
        bx,by=fx+205,fy-120
        for k in range(6):d.ellipse((bx-40-k*20,by+20+math.sin(k)*12,bx-36-k*20,by+24+math.sin(k)*12),fill="#e3bd73")
        d.ellipse((bx-21,by-23,bx+21,by+23),fill="#fff4b9")
        d.ellipse((bx-24,by-32,bx,by-10),fill="#e6efe0")
        d.ellipse((bx+2,by-32,bx+26,by-10),fill="#e6efe0")
        d.ellipse((bx-5,by-6,bx+5,by+8),fill="#b2a264")
    elif theme == "space":
        # Starlit indigo sky, cream moons and dusty-lilac ground.
        for i in range(76):
            x,y=rng.randint(45,1240),rng.randint(30,675)
            r=rng.choice([1.5,2,3,4])
            if i%8==0:_star(d,x,y,r*2,"#f6e4ba")
            else:d.ellipse((x-r,y-r,x+r,y+r),fill="#e5e3d5")
        d.ellipse((900,100,1123,322),fill="#e8c794")
        d.ellipse((930,126,1097,292),fill="#edcfa4")
        d.ellipse((960,147,999,185),fill="#dcbf95")
        d.ellipse((1025,223,1080,265),fill="#dcbf95")
        d.arc((838,165,1190,264),0,360,fill="#c4c2d2",width=11)
        d.ellipse((149,277,271,398),fill="#a8c8ce")
        d.arc((161,296,261,375),10,175,fill="#d3e3d8",width=9)
        _hill(d,w,747,45,"#888fae",.2)
        _hill(d,w,813,42,"#aaa8bf",1.7)
        _hill(d,w,925,37,"#c9c1cf",2.2)
        for x,y,rx,ry in [(205,843,72,16),(1058,884,88,20),(818,828,32,8)]:
            d.ellipse((x-rx,y-ry,x+rx,y+ry),fill="#a49bb7")
            d.arc((x-rx,y-ry-3,x+rx,y+ry),180,360,fill="#dcd0d8",width=3)
        # A friendly paper-shaped rocket changes sides to vary the scenes.
        rx,ry=300+(index%2)*700,635
        d.rounded_rectangle((rx-44,ry-146,rx+44,ry+57),radius=35,fill="#f3e6d1")
        d.polygon([(rx-42,ry-119),(rx,ry-210),(rx+42,ry-119)],fill="#cf907b")
        d.polygon([(rx-43,ry-3),(rx-83,ry+70),(rx-41,ry+49)],fill="#cf907b")
        d.polygon([(rx+43,ry-3),(rx+83,ry+70),(rx+41,ry+49)],fill="#cf907b")
        d.ellipse((rx-25,ry-100,rx+25,ry-50),fill="#90b7c1",outline="#d9c4ad",width=6)
        d.ellipse((rx-11,ry-92,rx+6,ry-75),fill="#c6e4e3")
        _fox(d,584+index%3*36,714,1.32,space=True)
        # The same mint robot with a glowing heart, a useful recurring friend.
        x,y=860,689
        d.rounded_rectangle((x-47,y-42,x+47,y+29),radius=18,fill="#93b9b2")
        d.rounded_rectangle((x-34,y-29,x+34,y+9),radius=12,fill="#3b5968")
        d.ellipse((x-23,y-18,x-12,y-7),fill="#f5db9a")
        d.ellipse((x+12,y-18,x+23,y-7),fill="#f5db9a")
        d.rounded_rectangle((x-33,y+32,x+33,y+102),radius=14,fill="#bdd0bf")
        _star(d,x,y+65,11,"#f8dfa1")
        d.line((x,y-43,x,y-68),fill="#93b9b2",width=5)
        d.ellipse((x-8,y-81,x+8,y-65),fill="#f4d893")
        for dx in (-28,14):d.rounded_rectangle((x+dx,y+93,x+dx+15,y+122),radius=6,fill="#7d9b9d")
    else:
        # Filtered surface light and layers of coral make a calm underwater spread.
        for x in [220,430,700,1020]:d.polygon([(x,0),(x+32,0),(x+228,775),(x-10,775)],fill="#e2f4e927")
        for i in range(36):
            x,y=rng.randint(80,1210),rng.randint(90,720);r=rng.randint(4,14)
            d.ellipse((x-r,y-r,x+r,y+r),outline="#d8efdfaa",width=2)
        _hill(d,w,749,46,"#65adae",.6)
        _hill(d,w,846,40,"#9ec7ba",2)
        _hill(d,w,918,43,"#e3dbb7",1.2)
        for x,s,c in [(95,1.4,"#628f8c"),(210,.8,"#77a58b"),(1115,1.3,"#618e8d"),(1220,.9,"#7ead94")]:
            for dx in (-38,0,37):
                pts=[(x+dx+math.sin(t/35+dx)*15,910-t) for t in range(0,int(250*s),12)]
                d.line(pts,fill=c,width=int(12*s))
        for x,y,s in [(220,914,1.0),(1025,901,1.0),(1160,884,.65)]:
            for dx,dy in [(-43,-68),(0,-100),(38,-57),(-15,-35)]:
                d.line([(x,y),(x+dx*s*.5,y+dy*s*.55),(x+dx*s,y+dy*s)],fill="#dcaa95",width=int(12*s))
                d.ellipse((x+dx*s-7,y+dy*s-8,x+dx*s+7,y+dy*s+6),fill="#ecc4ab")
        for i in range(7):
            x=285+i*100;y=285+math.sin(i+index)*55
            d.ellipse((x-22,y-12,x+22,y+12),fill="#f2cc91")
            d.polygon([(x+16,y),(x+35,y-15),(x+35,y+15)],fill="#ecc496")
            d.ellipse((x-13,y-3,x-9,y+1),fill="#446f79")
        _fox(d,560+index%3*36,726,1.27)
        # Crystal dome indicates the fox is safely exploring underwater.
        d.arc((443+index%3*36,562,701+index%3*36,784),190,360,fill="#d1efdf",width=4)
        x,y=840,690
        d.ellipse((x-65,y-45,x+65,y+45),fill="#72a99a")
        d.ellipse((x-51,y-34,x+51,y+32),fill="#9dc4a5")
        d.polygon([(x,y-27),(x+31,y-9),(x+24,y+22),(x-21,y+25),(x-36,y-4)],outline="#78a18b",fill="#a9caa5")
        d.ellipse((x+46,y-11,x+100,y+30),fill="#c4d7ad")
        d.ellipse((x+80,y+1,x+86,y+8),fill="#426c6b")
        for dx,dy in [(-38,32),(25,35),(-40,-37),(22,-42)]:d.ellipse((x+dx-13,y+dy-5,x+dx+17,y+dy+13),fill="#a7c8a5")
        if index%3==0:
            d.arc((981,713,1106,834),180,360,fill="#e5bf9d",width=30)
            d.ellipse((1029,759,1064,791),fill="#f8edd5")
        elif index%3==1:
            _star(d,1043,820,40,"#e7b294")
    # A quiet frame is used consistently across all 24 illustrations.
    d.rounded_rectangle((25,25,w-25,h-25),radius=22,outline="#fff9e830",width=2)
    img=Image.alpha_composite(img.convert("RGBA"),layer.resize((w,h),Image.Resampling.LANCZOS)).convert("RGB")
    img=img.resize((1200,900),Image.Resampling.LANCZOS)
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    img.save(destination,"PNG",optimize=True)
    return destination


def _url(project_dir: Path, filename: str) -> str:
    return f"/files/projects/{quote(project_dir.name)}/{quote(filename)}"


def _local_url_path(url: str, project_dir: Path) -> Path:
    from urllib.parse import unquote
    if url.startswith(f"/files/projects/{quote(project_dir.name)}/"):
        name=unquote(url.rsplit("/",1)[-1]);candidate=project_dir/name
    elif url.startswith("/files/library/"):
        candidate=LIBRARY/unquote(url.removeprefix("/files/library/"))
    else:
        raise RuntimeError("媒体导出需要已经下载到本地的图片/音频，请先生成项目素材。")
    allowed=project_dir.resolve() if "/files/projects/" in url else LIBRARY.resolve()
    if not candidate.resolve().is_relative_to(allowed) or not candidate.is_file():
        raise RuntimeError(f"本地媒体文件不存在：{candidate.name}")
    return candidate


def render_demo_images(project: dict, project_dir: Path) -> dict:
    project_dir=Path(project_dir);project_dir.mkdir(parents=True,exist_ok=True)
    theme=project.get("theme") or project.get("inputs",{}).get("theme","forest")
    theme=theme if theme in PALETTES else "forest"
    reused=0;drawn=0
    for i,scene in enumerate(project.get("scenes",[])):
        filename=f"scene-{i+1:02d}.png"
        # Library images illustrate a theme; they are not generated from the
        # current scene description and do not prove prompt/image alignment.
        seed=LIBRARY/"images"/f"{theme}-{i%8+1:02d}.png"
        if seed.is_file():
            shutil.copyfile(seed,project_dir/filename)
            scene["image_asset_url"]=f"/files/library/images/{seed.name}"
            reused+=1
        else:
            draw_demo_illustration(theme,i,project_dir/filename,scene.get("title",""))
            scene.pop("image_asset_url",None)
            drawn+=1
        scene["image_url"]=_url(project_dir,filename)
        scene["image_source"]="local_program_demo"
        scene["image_note"]="本地程序插画主题示例，可跨场景复用；未按当前场景文字逐图生成。"
    if project.get("scenes"):
        project["cover_url"]=project["scenes"][0]["image_url"]
    project.setdefault("generation_proof",{})["images"]={"source":"local_program_demo","label":"本地程序绘制插画主题示例，非 AI 生成；不保证与各幕文字精准对应","consistent_character":"橘色小狐狸、奶油白脸颊和尾尖、青绿色围巾、金色背包","count":len(project.get("scenes",[])),"reused_library_count":reused,"newly_drawn_count":drawn,"scene_alignment":"theme_demo_only"}
    return project

async def _async_log(log, message):
    if log:
        value=log(message)
        if inspect.isawaitable(value):await value


def _sync_log(log,message):
    if log:
        value=log(message)
        if inspect.isawaitable(value):
            try:asyncio.get_running_loop().create_task(value)
            except RuntimeError:asyncio.run(value)


def _run_ffmpeg(args: list[str], timeout=300) -> subprocess.CompletedProcess:
    kwargs={"creationflags":subprocess.CREATE_NO_WINDOW} if os.name=="nt" else {}
    result=subprocess.run([ffmpeg_path(),"-hide_banner","-loglevel","error","-y",*map(str,args)],capture_output=True,timeout=timeout,**kwargs)
    if result.returncode:
        error=result.stderr.decode("utf-8",errors="replace")[-1800:]
        raise RuntimeError(f"FFmpeg 媒体处理失败：{error}")
    return result


def _pcm_from_audio(path: Path) -> bytes:
    return _run_ffmpeg(["-i",str(path),"-f","s16le","-acodec","pcm_s16le","-ac","1","-ar",str(SAMPLE_RATE),"pipe:1"]).stdout


def _write_wav(path: Path, pcm: bytes):
    with wave.open(str(path),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(SAMPLE_RATE);f.writeframes(pcm)


def _voice_map(project: dict) -> dict[str,str]:
    characters=project.get("characters",[])
    result={"旁白":VOICE_POOL[0],"narrator":VOICE_POOL[0]}
    non_narrator=0
    for ch in characters:
        name=ch.get("name") or ch.get("id") or "伙伴"
        role=str(ch.get("role","")).lower()
        is_narrator=role in {"narrator","旁白"} or name in {"旁白","叙述者"}
        voice=ch.get("voice")
        if voice not in VOICE_POOL:
            voice=VOICE_POOL[0] if is_narrator else VOICE_POOL[1+non_narrator%(len(VOICE_POOL)-1)]
        if not is_narrator:non_narrator+=1
        result[name]=voice
        if ch.get("id"):result[ch["id"]]=voice
        ch["voice"]=voice
    return result


def speech_prosody(emotion: str = "") -> dict[str, str]:
    """Small prosody adjustments, not a provider-native emotional style."""
    value = str(emotion).lower()
    choices = [
        (("低语", "轻声", "whisper"), {"rate":"-15%", "pitch":"-4Hz", "volume":"-8%"}),
        (("担心", "害怕", "紧张", "悲伤", "sad", "worried"), {"rate":"-12%", "pitch":"-3Hz", "volume":"+0%"}),
        (("兴奋", "开心", "快乐", "高兴", "happy", "excited"), {"rate":"+3%", "pitch":"+4Hz", "volume":"+0%"}),
        (("坚定", "勇敢", "鼓励", "brave", "confident"), {"rate":"-3%", "pitch":"+1Hz", "volume":"+0%"}),
    ]
    for terms, parameters in choices:
        if any(term in value for term in terms):
            return dict(parameters)
    return {"rate":"-8%", "pitch":"+0Hz", "volume":"+0%"}


async def _save_speech(edge_tts, text, voice, destination, emotion=""):
    options={"text":text,"voice":voice,**speech_prosody(emotion)}
    if "boundary" in inspect.signature(edge_tts.Communicate).parameters:
        options["boundary"]="WordBoundary"
    communicator=edge_tts.Communicate(**options)
    boundaries=[]
    with destination.open("wb") as output:
        async for message in communicator.stream():
            if message["type"]=="audio":output.write(message["data"])
            elif message["type"] in {"WordBoundary","SentenceBoundary"}:
                boundaries.append({"start":message["offset"]/10_000_000,"end":(message["offset"]+message["duration"])/10_000_000,"text":message.get("text","")})
    # WordBoundary can omit punctuation and whitespace. Restore the exact source
    # text between aligned words without estimating or altering their timestamps.
    positions=[];cursor=0
    for boundary in boundaries:
        position=text.find(boundary["text"],cursor)
        if position<0:positions=[];break
        positions.append(position);cursor=position+len(boundary["text"])
    if positions:
        for i,boundary in enumerate(boundaries):
            start=0 if i==0 else positions[i]
            end=positions[i+1] if i+1<len(positions) else len(text)
            boundary["text"]=text[start:end]
    return boundaries


def _audio_cache_key(project):
    voices=_voice_map(project)
    content=[{'scene_id':s['scene_id'],'lines':[{'character':r.get('character','旁白'),'text':str(r['text']).strip(),'voice':voices.get(r.get('character','旁白')),'emotion':r.get('emotion') or s.get('mood') or '温柔','prosody':speech_prosody(r.get('emotion') or s.get('mood') or '温柔')} for r in s.get('dialogues',[])]} for s in project['scenes']]
    return hashlib.sha256(json.dumps({'engine':'edge-tts-pcm-24000-v1','content':content},sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def write_audio_cache(project, folder):
    folder=Path(folder)
    fields=('audio_url','duration','segments','audio_proof')
    state={k:project[k] for k in fields}
    scene_states=[{k:s[k] for k in ('audio_url','duration','segments')} for s in project['scenes']]
    names=['story-audio.mp3']+[f'scene-{i+1:02}.mp3' for i in range(len(project['scenes']))]
    files={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in names}
    record={'input_sha256':_audio_cache_key(project),'state':state,'scenes':scene_states,'files':files}
    (folder/'audio-cache.json').write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')


def load_audio_cache(project, folder):
    folder=Path(folder)
    try:
        record=json.loads((folder/'audio-cache.json').read_text(encoding='utf-8'))
        if record['input_sha256']!=_audio_cache_key(project):return False
        if not record['state']['audio_proof']['real_tts']:return False
        if len(record['state']['audio_proof']['voices'])<3:return False
        if len(record['scenes'])!=len(project['scenes']):return False
        required={'story-audio.mp3'}|{f'scene-{i+1:02}.mp3' for i in range(len(project['scenes']))}
        if set(record['files'])!=required:return False
        for name,digest in record['files'].items():
            if Path(name).name!=name or hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:return False
        if record['files']['story-audio.mp3']!=record['state']['audio_proof']['sha256']:return False
        project.update(record['state'])
        for scene,state in zip(project['scenes'],record['scenes']):scene.update(state)
        return True
    except (KeyError,ValueError,TypeError,OSError):return False


async def generate_audio(project: dict, project_dir: Path, log=None) -> dict:
    """Voice every supplied dialogue with stable roles and measurable timings.

    Each TTS part is decoded to PCM before concatenation: segments are measured
    from actual samples, never estimated from character count. Three distinct
    roles are required for the course's three-voice deliverable.
    """
    try:import edge_tts
    except ImportError as exc:raise RuntimeError("尚未安装 edge-tts，请先安装项目依赖。") from exc
    ffmpeg_path()
    project_dir=Path(project_dir);project_dir.mkdir(parents=True,exist_ok=True)
    if load_audio_cache(project,project_dir):
        await _async_log(log,'复用已校验真实配音缓存：正文、角色音色、情感参数与MP3哈希全部一致；未重新请求TTS。')
        return project
    voices=_voice_map(project)
    dialogues=[]
    for scene in project.get("scenes",[]):
        rows=scene.get("dialogues",[])
        if not rows:raise RuntimeError("场景没有角色对话，请先生成包含旁白、主角和伙伴的完整故事。")
        for row in rows:
            who=str(row.get("character") or "旁白")
            if who not in voices:voices[who]=VOICE_POOL[1+(len(voices)%(len(VOICE_POOL)-1))]
            if str(row.get("text","")).strip():dialogues.append((who,str(row["text"]).strip(),voices[who]))
    used=sorted({voice for _,_,voice in dialogues})
    if len(used)<3:raise RuntimeError("三音色配音需要旁白、主角、伙伴至少三个实际说话角色，请完善故事对话后重试。")
    work=project_dir/"audio_parts";work.mkdir(exist_ok=True)
    all_pcm=bytearray();all_segments=[];part_index=0;proof_parts=[]
    gap=b"\0\0"*int(SAMPLE_RATE*.12)
    for si,scene in enumerate(project["scenes"]):
        scene_pcm=bytearray();scene_segments=[];scene_start=len(all_pcm)/(SAMPLE_RATE*2)
        for row in scene.get("dialogues",[]):
            text=str(row.get("text","")).strip()
            if not text:continue
            who=str(row.get("character") or "旁白");voice=voices[who]
            emotion=str(row.get("emotion") or scene.get("mood") or "温柔")
            prosody=speech_prosody(emotion)
            part_index+=1;part=work/f"part-{part_index:03d}.mp3"
            await _async_log(log,f"真实配音 {part_index}/{len(dialogues)} · {who} · {voice}")
            try:
                boundaries=await asyncio.wait_for(_save_speech(edge_tts,text,voice,part,emotion),timeout=100)
                if not part.is_file() or part.stat().st_size<500:raise RuntimeError("服务未返回有效音频")
                pcm=await asyncio.to_thread(_pcm_from_audio,part)
                if len(pcm)<SAMPLE_RATE//2:raise RuntimeError("返回音频时长异常")
            except Exception as exc:
                raise RuntimeError(f"Edge TTS 真实配音失败（{who}/{voice}）。请检查网络后重试；本项目不会以静音替代配音。原因：{type(exc).__name__}: {str(exc)[:180]}") from exc
            start=len(scene_pcm)/(SAMPLE_RATE*2);duration=len(pcm)/(SAMPLE_RATE*2)
            word_segments=[{"start":round(start+min(duration,b["start"]),3),"end":round(start+min(duration,b["end"]),3),"text":b["text"]} for b in boundaries]
            seg={"start":round(start,3),"end":round(start+duration,3),"text":text,"character":who,"voice":voice,"emotion":emotion,"prosody":prosody,"words":word_segments}
            scene_segments.append(seg)
            all_segments.append({**seg,"start":round(scene_start+start,3),"end":round(scene_start+start+duration,3),"scene_index":si,"words":[{**w,"start":round(w["start"]+scene_start,3),"end":round(w["end"]+scene_start,3)} for w in word_segments]})
            scene_pcm.extend(pcm);scene_pcm.extend(gap)
            proof_parts.append({"file":str(part.relative_to(project_dir)),"voice":voice,"character":who,"emotion":emotion,"prosody":prosody,"duration":round(duration,3),"sha256":hashlib.sha256(part.read_bytes()).hexdigest(),"characters":len(text)})
        wav=work/f"scene-{si+1:02d}.wav";_write_wav(wav,bytes(scene_pcm))
        scene_file=project_dir/f"scene-{si+1:02d}.mp3"
        await asyncio.to_thread(_run_ffmpeg,["-i",str(wav),"-c:a","libmp3lame","-q:a","3",str(scene_file)])
        scene["audio_url"]=_url(project_dir,scene_file.name)
        scene["duration"]=round(len(scene_pcm)/(SAMPLE_RATE*2),3)
        scene["segments"]=scene_segments
        all_pcm.extend(scene_pcm)
    full_wav=work/"narration.wav";_write_wav(full_wav,bytes(all_pcm))
    full=project_dir/"story-audio.mp3"
    await asyncio.to_thread(_run_ffmpeg,["-i",str(full_wav),"-c:a","libmp3lame","-q:a","2",str(full)])
    duration=len(all_pcm)/(SAMPLE_RATE*2)
    project["audio_url"]=_url(project_dir,full.name)
    project["duration"]=round(duration,3)
    project["segments"]=all_segments
    project["audio_proof"]={"provider":"Microsoft Edge TTS","real_tts":True,"prosody_method":"rate/pitch/volume parameters; not native emotion-style synthesis","voices":used,"role_voices":voices,"duration":round(duration,3),"timing_source":"decoded PCM samples at 24000 Hz","created_at":datetime.now(timezone.utc).isoformat(),"parts":proof_parts,"sha256":hashlib.sha256(full.read_bytes()).hexdigest()}
    (project_dir/"audio-proof.json").write_text(json.dumps(project["audio_proof"],ensure_ascii=False,indent=2),encoding="utf-8")
    write_audio_cache(project,project_dir)
    await _async_log(log,f"真实三角色配音完成 · {duration:.1f} 秒 · {len(used)} 种音色")
    return project


def _wrap_pixels(text: str, font, width: int, draw) -> list[str]:
    lines=[];line=""
    for char in text:
        if char=="\n":lines.append(line);line="";continue
        candidate=line+char
        if line and draw.textlength(candidate,font=font)>width:lines.append(line);line=char
        else:line=candidate
    if line:lines.append(line)
    return lines


def _subtitle_cards(project, project_dir):
    """Write timed, transparent Chinese text cards; no ImageMagick is involved."""
    cards=project_dir/"video_work";cards.mkdir(exist_ok=True)
    timeline=[]
    for i,seg in enumerate(project.get("segments",[])):
        duration=float(seg["end"])-float(seg["start"])
        exact_chunks=[]
        if seg.get("words"):
            current="";chunk_start=None;chunk_end=None
            for word in seg["words"]:
                if chunk_start is None:chunk_start=word["start"]
                current+=word["text"];chunk_end=word["end"]
                if len(current)>=28 or (len(current)>=12 and current[-1] in "，。！？；!?,;"):
                    exact_chunks.append((current,chunk_start,chunk_end));current="";chunk_start=None
            if current:exact_chunks.append((current,chunk_start,chunk_end))
        # Split long turns at punctuation, then into short readable two-line cards.
        chunks=[];current=""
        for piece in re.findall(r"[^，。！？；、：,!?;:]+[，。！？；、：,!?;:]?|[，。！？]",seg["text"]):
            if len(current)+len(piece)>35 and current:chunks.append(current);current=""
            while len(piece)>40:
                if current:chunks.append(current);current=""
                chunks.append(piece[:35]);piece=piece[35:]
            current+=piece
        if current:chunks.append(current)
        if not chunks:chunks=[seg["text"]]
        total=sum(len(s) for s in chunks);start=float(seg["start"])
        timed_chunks=exact_chunks or [(chunk,None,None) for chunk in chunks]
        for ci,(chunk,exact_start,exact_end) in enumerate(timed_chunks):
            if exact_start is not None:start=exact_start
            end=exact_end if exact_end is not None else start+duration*len(chunk)/total
            im=Image.new("RGBA",(1280,720),(0,0,0,0));d=ImageDraw.Draw(im)
            font=_font(28);lines=_wrap_pixels(chunk,font,1030,d)
            height=30+len(lines)*42
            d.rounded_rectangle((80,700-height,1200,706),radius=18,fill=(26,40,47,212))
            for li,line in enumerate(lines):
                tw=d.textlength(line,font=font)
                d.text(((1280-tw)/2,711-height+li*42),line,font=font,fill="#fff9eb")
            path=cards/f"sub-{i:03d}-{ci:02d}.png";im.save(path)
            timeline.append({"path":path,"start":round(start,3),"end":round(end,3),"text":chunk})
            start=end
    return timeline


def _frame_schedule(frames, cards, duration, fps=24):
    """Yield only the current scene/caption indexes; memory is O(scene+caption metadata)."""
    scene_index=0;scene_end=float(frames[0][1]);card_index=0
    for frame_number in range(math.ceil(duration*fps)):
        timestamp=frame_number/fps
        while scene_index+1<len(frames) and timestamp>=scene_end:
            scene_index+=1;scene_end+=float(frames[scene_index][1])
        while card_index<len(cards) and float(cards[card_index]["end"])<=timestamp:
            card_index+=1
        active=card_index if card_index<len(cards) and float(cards[card_index]["start"])<=timestamp<float(cards[card_index]["end"]) else None
        yield scene_index,active


def _process_peak_memory_mb(process):
    if os.name!="nt":return None
    try:
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ("PeakWorkingSetSize","WorkingSetSize","QuotaPeakPagedPoolUsage","QuotaPagedPoolUsage","QuotaPeakNonPagedPoolUsage","QuotaNonPagedPoolUsage","PagefileUsage","PeakPagefileUsage")]
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        query=ctypes.windll.psapi.GetProcessMemoryInfo
        query.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD];query.restype=wintypes.BOOL
        if query(wintypes.HANDLE(int(process._handle)),ctypes.byref(counters),counters.cb):
            return round(counters.PeakWorkingSetSize/(1024*1024),2)
    except Exception:
        pass
    return None


def _encode_streamed_video(frames,cards,narration,music,destination,duration,log=None):
    """Block on a bounded OS pipe; never buffer two sparse FFmpeg video timelines.

    Only the current background, caption and one RGB frame are held in Python.
    FFmpeg receives one constant-rate video stream and two file audio streams.
    Its input queue is limited to two raw frames and its encoder to one thread.
    """
    fps=24;cards=sorted(cards,key=lambda card:(card["start"],card["end"]))
    temporary=destination.with_name(destination.stem+".rendering.mp4")
    error_file=destination.parent/"video_work"/"ffmpeg-stream.log"
    filters="[1:a]volume=1.0[n];[2:a]volume=0.10[m];[n][m]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[a]"
    command=[ffmpeg_path(),"-hide_banner","-loglevel","error","-y","-thread_queue_size","2","-f","rawvideo","-pixel_format","rgb24","-video_size","1280x720","-framerate",str(fps),"-i","pipe:0","-i",str(narration),"-stream_loop","-1","-i",str(music),"-filter_complex_threads","1","-filter_complex",filters,"-map","0:v:0","-map","[a]","-t",f"{duration:.3f}","-r",str(fps),"-c:v","libx264","-threads","1","-preset","veryfast","-crf","21","-x264-params","rc-lookahead=10:sync-lookahead=0","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-movflags","+faststart",str(temporary)]
    kwargs={"creationflags":subprocess.CREATE_NO_WINDOW} if os.name=="nt" else {}
    started=time.perf_counter();frame_count=0;peak_mb=None;base=None;last_scene=None;last_key=None;frame_bytes=None
    with error_file.open("wb") as errors:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors,**kwargs)
        try:
            for scene_index,caption_index in _frame_schedule(frames,cards,duration,fps):
                key=(scene_index,caption_index)
                if key!=last_key:
                    if scene_index!=last_scene:
                        if base is not None:base.close()
                        with Image.open(frames[scene_index][0]) as source:base=source.convert("RGBA")
                        last_scene=scene_index
                    if caption_index is None:
                        rgb=base.convert("RGB")
                    else:
                        with Image.open(cards[caption_index]["path"]) as source:
                            caption=source.convert("RGBA")
                        composed=Image.alpha_composite(base,caption);caption.close()
                        rgb=composed.convert("RGB");composed.close()
                    frame_bytes=rgb.tobytes();rgb.close();last_key=key
                process.stdin.write(frame_bytes)
                frame_count+=1
                if frame_count%fps==0:
                    sample=_process_peak_memory_mb(process)
                    if sample is not None:peak_mb=max(peak_mb or 0,sample)
                if frame_count%(fps*60)==0:
                    _sync_log(log,f"流式合成进度 {frame_count/fps:.0f}/{duration:.0f} 秒（当前帧即时编码）")
                if time.perf_counter()-started>max(600,duration*12):
                    raise TimeoutError("视频流式编码超时")
            process.stdin.close()
            code=process.wait(timeout=max(120,int(duration*2)))
            sample=_process_peak_memory_mb(process)
            if sample is not None:peak_mb=max(peak_mb or 0,sample)
            if code:raise RuntimeError(f"编码器退出码 {code}")
        except Exception as exc:
            if process.poll() is None:process.kill()
            process.wait(timeout=20)
            try:process.stdin.close()
            except OSError:pass
            errors.flush()
            detail=error_file.read_text(encoding="utf-8",errors="replace")[-1800:]
            raise RuntimeError(f"FFmpeg 流式视频合成失败：{exc} {detail}") from exc
        finally:
            if base is not None:base.close()
    if not temporary.is_file() or temporary.stat().st_size<50000:
        raise RuntimeError("视频导出失败，未产生有效 MP4。")
    temporary.replace(destination)
    return {"encoding":"bounded_rawvideo_pipe","encoder_threads":1,"input_queue_frames":2,"rendered_frames":frame_count,"render_seconds":round(time.perf_counter()-started,3),"ffmpeg_peak_working_set_mb":peak_mb}


def _video_cache_key(project, folder):
    from .evidence import file_digest
    folder=Path(folder)
    theme=project.get('theme') or project['inputs']['theme']
    images=[{'sha256':file_digest(_local_url_path(s['image_url'],folder)),'title':s.get('title'),'duration':s['duration']} for s in project['scenes']]
    content={'renderer':'bounded-stream-1thread-veryfast-v2','images':images,'audio':file_digest(_local_url_path(project['audio_url'],folder)),'segments':project['segments'],'music':file_digest(LIBRARY/'sounds'/f'bgm-{theme}.wav'),'theme':theme}
    return hashlib.sha256(json.dumps(content,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def write_video_cache(project, folder):
    from .evidence import file_digest
    folder=Path(folder)
    record={'input_sha256':_video_cache_key(project,folder),'video_sha256':file_digest(folder/'story-video.mp4'),'video_url':project['video_url'],'video_proof':project['video_proof']}
    (folder/'video-cache.json').write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')


def load_video_cache(project, folder):
    from .evidence import file_digest
    folder=Path(folder)
    try:
        record=json.loads((folder/'video-cache.json').read_text(encoding='utf-8'))
        if record['input_sha256']!=_video_cache_key(project,folder):return False
        actual=file_digest(folder/'story-video.mp4')
        if record['video_sha256']!=actual or record['video_proof']['sha256']!=actual:return False
        project.update(video_url=record['video_url'],video_proof=record['video_proof'])
        return True
    except (KeyError,ValueError,TypeError,OSError):return False


def render_video(project: dict, project_dir: Path, log=None) -> dict:
    """Render a real narrated MP4 with visible Chinese captions and quiet music.

    Narration must already last at least 60 seconds. We do not pad a short voice
    track with silence or blank frames to claim that duration requirement.
    """
    project_dir=Path(project_dir)
    if not project.get("audio_url") or not project.get("audio_proof",{}).get("real_tts"):
        raise RuntimeError("视频需要已完成的真实角色配音，请先生成音频。")
    duration=float(project.get("duration",0))
    if duration<60:raise RuntimeError(f"真实旁白仅 {duration:.1f} 秒，少于 60 秒。请增加情节与对话后重新配音，视频不会自动补静音或空白。")
    if not project.get("segments"):raise RuntimeError("缺少与配音对应的时间字幕，请重新生成真实配音。")
    if load_video_cache(project,project_dir):
        _sync_log(log,"复用已核验视频缓存：图片、音频、字幕时间轴和MP4哈希一致；本次仅重新导出PDF。")
        return project
    work=project_dir/"video_work";work.mkdir(exist_ok=True)
    scenes=project.get("scenes",[])
    if not scenes:raise RuntimeError("没有可合成的绘本场景，请先生成完整故事与插画。")
    frames=[]
    for i,scene in enumerate(scenes):
        image_path=_local_url_path(scene.get("image_url",""),project_dir)
        scene_duration=float(scene.get("duration",0))
        if scene_duration<=0:raise RuntimeError("场景缺少真实音频时长，请重新生成配音。")
        _sync_log(log,f"合成绘本画面 {i+1}/{len(scenes)} · {scene_duration:.1f} 秒")
        # A full illustration on a matching blurred background keeps every crop safe.
        with Image.open(image_path) as original:
            source=original.convert("RGB")
            from PIL import ImageOps
            background=ImageOps.fit(source,(1280,720)).filter(ImageFilter.GaussianBlur(26))
            foreground=ImageOps.contain(source,(1008,704))
            background.paste(foreground,((1280-foreground.width)//2,(720-foreground.height)//2))
            # Child-friendly chapter label has a quiet cream backing.
            d=ImageDraw.Draw(background)
            title=f"{i+1:02d}  {scene.get('title','故事场景')}"
            font=_font(21,True)
            while len(title)>4 and d.textlength(title,font=font)>1150:title=title[:-2]+"…"
            tw=d.textlength(title,font=font)
            d.rounded_rectangle((28,24,57+tw,67),radius=15,fill="#fff6e6")
            d.text((42,31),title,font=font,fill=PALETTES.get(project.get("theme"),PALETTES["forest"])["ink"])
            frame=work/f"frame-{i+1:02d}.png";background.save(frame)
        frames.append((frame,scene_duration))
    cards=_subtitle_cards(project,project_dir)
    narration=_local_url_path(project["audio_url"],project_dir)
    theme=project.get("theme") or project.get("inputs",{}).get("theme","forest")
    music=LIBRARY/"sounds"/f"bgm-{theme}.wav"
    if not music.is_file():raise RuntimeError("本地背景音乐素材缺失，请先运行 scripts/seed_assets.py。")
    destination=project_dir/"story-video.mp4"
    _sync_log(log,f"混合真实配音与轻柔背景音乐，绘制 {len(cards)} 条中文字幕")
    metrics=_encode_streamed_video(frames,cards,narration,music,destination,duration,log)
    project["video_url"]=_url(project_dir,destination.name)
    project["video_proof"]={"duration":duration,"fps":24,"resolution":"1280x720","subtitle_count":len(cards),"subtitle_renderer":"Pillow / Windows Chinese font",**metrics,"narration":"real Edge TTS","background_music":music.name,"voices":project["audio_proof"]["voices"],"sha256":hashlib.sha256(destination.read_bytes()).hexdigest()}
    (project_dir/"video-proof.json").write_text(json.dumps(project["video_proof"],ensure_ascii=False,indent=2),encoding="utf-8")
    write_video_cache(project,project_dir)
    _sync_log(log,f"视频完成 · {duration:.1f} 秒 · 真实三角色配音 + 中文同步字幕 + 背景音乐")
    return project


def render_pdf(project: dict, project_dir: Path) -> Path:
    """Export a designed landscape children's book with embedded Chinese font."""
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.colors import HexColor, Color
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from xml.sax.saxutils import escape
    font_path=Path(os.environ.get("WINDIR","C:/Windows"))/"Fonts"/"simhei.ttf"
    if not font_path.exists():raise RuntimeError("PDF 导出缺少可嵌入的中文字体 simhei.ttf。")
    if "StoryChinese" not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont("StoryChinese",str(font_path)))
    project_dir=Path(project_dir);project_dir.mkdir(exist_ok=True,parents=True)
    destination=project_dir/"storybook.pdf"
    width,height=864,648
    pdf=canvas.Canvas(str(destination),pagesize=(width,height),pageCompression=1)
    pdf.setTitle(project.get("title","星芽故事屋"));pdf.setAuthor("星芽故事屋 · 个性化绘本")
    palette=PALETTES.get(project.get("theme"),PALETTES["forest"])
    cream="#fcf7ec";ink=palette["ink"]
    def para(text,x,y,max_width,size=13,leading=22,color=ink,max_height=200):
        style=ParagraphStyle("body",fontName="StoryChinese",fontSize=size,leading=leading,textColor=HexColor(color),wordWrap="CJK",spaceAfter=0)
        p=Paragraph(escape(str(text)).replace("\n","<br/>"),style)
        pw,ph=p.wrap(max_width,max_height)
        if ph>max_height and size>10:return para(text,x,y,max_width,size-1,leading-1,color,max_height)
        p.drawOn(pdf,x,y-ph);return ph
    def background():
        pdf.setFillColor(HexColor(cream));pdf.rect(0,0,width,height,fill=1,stroke=0)
    def footer(page):
        pdf.setFillColor(HexColor("#8b9d91"));pdf.setFont("StoryChinese",9)
        pdf.drawString(38,23,"星芽故事屋  /  每一个孩子，都值得拥有自己的故事")
        pdf.drawRightString(width-38,23,f"{page:02d}")
    background()
    cover=project.get("cover_url") or project.get("scenes",[{}])[0].get("image_url")
    if cover:
        image_path=_local_url_path(cover,project_dir)
        pdf.drawImage(str(image_path),346,82,width=482,height=482,preserveAspectRatio=True,anchor="c",mask="auto")
    pdf.setFillColor(HexColor(palette["accent"]));pdf.roundRect(38,555,185,27,13,fill=1,stroke=0)
    pdf.setFillColor(HexColor(ink));pdf.setFont("StoryChinese",11);pdf.drawString(54,564,"A LITTLE STORY, A BIG HEART")
    title=project.get("title","小狐狸的星光旅程")
    para(title,38,510,300,30,44,max_height=180)
    inputs=project.get("inputs",{})
    para(f"献给 {inputs.get('name','每一位小小探险家')}\n把好奇心装进口袋，让勇气带我们出发。",42,286,270,13,23,max_height=110)
    para("个性化亲子阅读绘本",42,146,270,11,18,color="#7b8e83")
    footer(1);pdf.showPage()
    page_number=2
    for i,scene in enumerate(project.get("scenes",[])):
        text=scene.get("text") or "\n".join(f"{d.get('character','旁白')}：{d.get('text','')}" for d in scene.get("dialogues",[]))
        story_style=ParagraphStyle("scene-body",fontName="StoryChinese",fontSize=12.5,leading=21,textColor=HexColor(ink),wordWrap="CJK")
        remaining=Paragraph(escape(str(text)).replace("\n","<br/>"),story_style)
        first_page=True
        while remaining is not None:
            background()
            pdf.setFillColor(HexColor(palette["accent"]));pdf.roundRect(37,590,40,27,10,fill=1,stroke=0)
            pdf.setFillColor(HexColor(ink));pdf.setFont("StoryChinese",12);pdf.drawCentredString(57,599,f"{i+1:02d}")
            title=scene.get("title",f"第 {i+1} 幕")+("" if first_page else " · 续")
            para(title,89,618,710,21,29,max_height=36)
            image_y,image_h=(232,344) if first_page else (350,226)
            text_top,text_height=(211,162) if first_page else (326,276)
            _,needed=remaining.wrap(768,2000)
            if first_page and text_height < needed <= text_height+84:
                gain=needed-text_height
                image_y+=gain;image_h-=gain;text_top+=gain;text_height+=gain
            if scene.get("image_url"):
                image_path=_local_url_path(scene["image_url"],project_dir)
                pdf.saveState();clip=pdf.beginPath();clip.roundRect(37,image_y,790,image_h,18);pdf.clipPath(clip,stroke=0,fill=0)
                pdf.drawImage(str(image_path),37,image_y,width=790,height=image_h,preserveAspectRatio=True,anchor="c",mask="auto")
                pdf.restoreState()
            remaining.wrap(768,text_height)
            pieces=remaining.split(768,text_height)
            if not pieces:
                raise RuntimeError("PDF正文无法分页，请检查文本格式。")
            current=pieces[0];_,paragraph_height=current.wrap(768,text_height)
            current.drawOn(pdf,48,text_top-paragraph_height)
            remaining=pieces[1] if len(pieces)>1 else None
            footer(page_number);pdf.showPage();page_number+=1;first_page=False
    background()
    pdf.setFillColor(HexColor(palette["accent"]));pdf.circle(width/2,462,39,fill=1,stroke=0)
    pdf.setFont("StoryChinese",28);pdf.setFillColor(HexColor(ink));pdf.drawCentredString(width/2,451,"芽")
    para("故事读完了，新的发现才刚刚开始。",130,370,604,24,35,max_height=85)
    para(project.get("moral","保持好奇，认真倾听，和朋友一起发现世界的温柔。"),165,275,534,16,28,max_height=130)
    footer(page_number);pdf.save()
    project["pdf_url"]=_url(project_dir,destination.name)
    return destination
