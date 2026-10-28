"""Export the current video's exact caption timeline as a separate SRT."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from storybook.storage import load_project,project_dir
from storybook.media import _subtitle_cards

def stamp(value):
 ms=round(value*1000);hours,ms=divmod(ms,3600000);minutes,ms=divmod(ms,60000);seconds,ms=divmod(ms,1000)
 return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('project_id');args=parser.parse_args()
 p=load_project(args.project_id);root=project_dir(args.project_id)
 if not p.get('segments'):raise SystemExit('项目没有实际配音时间轴。')
 cards=_subtitle_cards(p,root)
 if p.get('video_proof') and len(cards)!=p['video_proof']['subtitle_count']:raise SystemExit('当前时间轴与视频字幕数量不一致，请先重新合成视频。')
 target=root/'subtitles.srt';target.write_text('\n\n'.join(f'{i}\n{stamp(c["start"])} --> {stamp(c["end"])}\n{c["text"]}' for i,c in enumerate(cards,1))+'\n',encoding='utf-8')
 print(f'{target}: {len(cards)} captions')
if __name__=='__main__':main()
