"""Rebuild the 18 local SVG storyboard examples; no model calls or downloads."""
from pathlib import Path
from html import escape
import json
root=Path(__file__).resolve().parents[1];out=root/'web/demo-scenes';out.mkdir(exist_ok=True)

def fox(x,y,s=1,pose='stand',flip=False):
 arm={'stand':'M70 170 Q100 192 111 173','point':'M70 169 Q110 140 130 119','listen':'M70 169 Q97 130 77 119','write':'M70 169 Q117 189 130 176','wave':'M70 169 Q110 140 98 106'}[pose]
 return f'''<g transform="translate({x} {y}) scale({-s if flip else s} {s})"><ellipse cy="233" rx="106" ry="15" fill="#384e3430"/><path d="M-46 188 Q-159 114-143 187 Q-130 238-39 220" fill="#e48b48"/><path d="M-141 164 Q-162 204-106 220 L-115 184Z" fill="#fff0d8"/><rect x="-74" y="137" width="57" height="79" rx="20" fill="#dfb44c" stroke="#bb8e38" stroke-width="4"/><ellipse cy="182" rx="64" ry="58" fill="#ee9c52"/><ellipse cy="194" rx="36" ry="35" fill="#fff1d8"/><ellipse cx="-33" cy="228" rx="23" ry="13" fill="#d77c40"/><ellipse cx="39" cy="228" rx="23" ry="13" fill="#d77c40"/><path d="M-81 67 L-79-34 Q-49-31-23 19 M23 19 Q56-30 84-33 L80 69" fill="#ef9b51" stroke="#d48543" stroke-width="3"/><path d="M-67 24 L-66-12-39 23 M43 22 L70-11 70 26" fill="#e9ad98"/><ellipse cy="77" rx="99" ry="79" fill="url(#fur)"/><path d="M-94 84 Q-65 58-19 104 Q0 117 17 104 Q63 58 94 84 Q91 151 0 154 Q-91 151-94 84" fill="#fff3de"/><ellipse cx="-41" cy="75" rx="23" ry="29" fill="#53382b"/><ellipse cx="41" cy="75" rx="23" ry="29" fill="#53382b"/><ellipse cx="-39" cy="80" rx="14" ry="20" fill="#916039"/><ellipse cx="43" cy="80" rx="14" ry="20" fill="#916039"/><ellipse cx="-48" cy="63" rx="9" ry="11" fill="#fff"/><ellipse cx="34" cy="63" rx="9" ry="11" fill="#fff"/><circle cx="-32" cy="87" r="4" fill="#fff"/><circle cx="50" cy="87" r="4" fill="#fff"/><ellipse cx="-67" cy="108" rx="18" ry="9" fill="#efb2a0"/><ellipse cx="67" cy="108" rx="18" ry="9" fill="#efb2a0"/><path d="M-10 109 Q0 101 10 109 Q0 122-10 109" fill="#634637"/><path d="M-15 125 Q0 140 16 125" fill="none" stroke="#754c38" stroke-width="3" stroke-linecap="round"/><path d="M-55 148 Q0 165 57 146 L56 165 Q0 182-55 167Z" fill="#5b9a84"/><path d="M30 166 L64 164 68 206 40 197Z" fill="#438b76"/><path d="{arm}" fill="none" stroke="#ee9c52" stroke-width="27" stroke-linecap="round"/></g>'''

def friend(theme,x,y,s=1):
 if theme=='forest':body='<ellipse cx="-24" cy="-9" rx="27" ry="17" fill="#fff9dfbb"/><ellipse cx="24" cy="-9" rx="27" ry="17" fill="#fff9dfbb"/><ellipse cy="18" rx="18" ry="26" fill="#e8c75b"/><ellipse cy="32" rx="13" ry="13" fill="#fff6a1"/><circle cy="-10" r="23" fill="#7a9c69"/><path d="M-12-29-18-44 M12-29 18-44" stroke="#517a55" stroke-width="3"/>'
 elif theme=='space':body='<rect x="-34" y="-36" width="68" height="57" rx="20" fill="#b6d8ca"/><rect x="-25" y="-25" width="50" height="29" rx="12" fill="#3f6072"/><rect x="-26" y="23" width="52" height="48" rx="15" fill="#cce2d4"/><path d="M-15 71-15 87 M15 71 15 87 M-26 35-43 48 M26 35 43 48 M0-36 0-54" stroke="#88b4ac" stroke-width="10" stroke-linecap="round"/><circle cy="-57" r="8" fill="#ffe5a0"/>'
 else:body='<ellipse cy="14" rx="61" ry="44" fill="#7fac8e"/><path d="M-43 0 0-21 42 0 25 42-25 42Z" fill="#b4cf98" stroke="#739d7e" stroke-width="4"/><ellipse cx="52" cy="-14" rx="27" ry="23" fill="#c4dcb0"/><ellipse cx="-35" cy="49" rx="22" ry="10" fill="#9abe9a"/><ellipse cx="35" cy="49" rx="22" ry="10" fill="#9abe9a"/>'
 eyes='<circle cx="-8" cy="-12" r="3" fill="#3b4f49"/><circle cx="8" cy="-12" r="3" fill="#3b4f49"/>' if theme!='ocean' else '<circle cx="57" cy="-19" r="4" fill="#3b4f49"/>'
 return f'<g transform="translate({x} {y}) scale({s})">{body}{eyes}</g>'

def home(theme,x,y):
 if theme=='forest':return f'<g transform="translate({x} {y})"><rect width="235" height="220" rx="25" fill="#ead2a9"/><path d="M-25 20 118-90 260 20Z" fill="#b67d61"/><rect x="83" y="110" width="67" height="110" rx="32" fill="#a97855"/><circle cx="54" cy="67" r="26" fill="#ffedb4"/><circle cx="185" cy="67" r="26" fill="#ffedb4"/></g>'
 if theme=='space':return f'<g transform="translate({x} {y})"><path d="M-15 220 Q-35-10 120-20 Q275-10 255 220Z" fill="#a2bdcf" stroke="#dbe9de" stroke-width="7"/><rect x="84" y="120" width="73" height="100" rx="25" fill="#f1c780"/><circle cx="58" cy="92" r="25" fill="#d6f0e5"/><circle cx="185" cy="92" r="25" fill="#d6f0e5"/></g>'
 return f'<g transform="translate({x} {y})"><path d="M-25 220 Q-85 12 45 13 Q120-95 197 13 Q320 12 260 220Z" fill="#e5b9aa"/><path d="M120 10 120 220 M40 20 80 220 M200 20 160 220" stroke="#c68f8e" stroke-width="6" fill="none"/><path d="M78 220 78 151 Q120 99 162 151 L162 220" fill="#8da8aa"/></g>'

def paper(x,y,s=1):return f'<g transform="translate({x} {y}) scale({s})"><path d="M0 0 64 13 122 0 180 16 172 121 116 108 57 122-8 105Z" fill="#fff0c8" stroke="#d8b882" stroke-width="4"/><path d="M22 78 Q46 16 83 60 T146 34" stroke="#91ad89" stroke-width="6" fill="none" stroke-dasharray="8 7"/><circle cx="30" cy="78" r="10" fill="#e9a16a"/><path d="M137 22 156 44 M156 22 137 44" stroke="#db8d69" stroke-width="5"/></g>'

def mentor(theme):
 if theme=='forest':return '<g><path d="M807 717 Q860 420 826 118 L996 118 Q955 435 1027 717Z" fill="#b79a70"/><ellipse cx="909" cy="160" rx="224" ry="145" fill="#81a780"/><circle cx="870" cy="403" r="12" fill="#675240"/><circle cx="950" cy="403" r="12" fill="#675240"/><path d="M884 454 Q913 482 942 454" stroke="#675240" stroke-width="7" fill="none"/><path d="M843 350 Q868 332 893 348 M924 348 Q949 332 974 350" fill="none" stroke="#d8c3a2" stroke-width="13" stroke-linecap="round"/></g>'
 if theme=='space':return '<g transform="translate(915 378)"><path d="M0-155 44-54 154-50 69 27 93 145 0 87-93 145-69 27-154-50-44-54Z" fill="#f4d27c"/><circle cx="-32" cy="-5" r="16" fill="none" stroke="#aa8052" stroke-width="5"/><circle cx="32" cy="-5" r="16" fill="none" stroke="#aa8052" stroke-width="5"/><path d="M-16-5 16-5 M-23 48 Q0 67 23 48" stroke="#805b45" stroke-width="5" fill="none"/></g>'
 return '<g transform="translate(900 380)"><ellipse rx="214" ry="117" fill="#8eb7c8"/><path d="M161-19 263-92 241 16 263 88 164 43Z" fill="#7da4bb"/><path d="M-64 74-11 154 54 81" fill="#7399af"/><path d="M-175 30 Q-73 121 126 54" fill="#c6dad4"/><circle cx="-105" cy="-16" r="9" fill="#3f6672"/><path d="M-144 39 Q-111 58-77 39" stroke="#486d76" stroke-width="4" fill="none"/></g>'

names=['发现小小愿望','与新伙伴出发','停下来找线索','请教智慧向导','朋友分工合作','满载发现回家']
for theme in ['forest','space','ocean']:
 for i in range(6):
  night=i==5; top,bottom=({'forest':('#d4e9d2','#fff1cb'),'space':('#334f7c','#8c9ec4'),'ocean':('#b7e6e1','#4796ac')}[theme]);
  if night:top,bottom=({'forest':('#536a86','#b1bea3'),'space':('#26375c','#7a81a3'),'ocean':('#386b90','#88b6b8')}[theme])
  defs=f'<defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient><radialGradient id="fur"><stop stop-color="#ffc984"/><stop offset="1" stop-color="#ed9951"/></radialGradient><radialGradient id="glow"><stop stop-color="#fff6ad" stop-opacity=".8"/><stop offset="1" stop-color="#fff6ad" stop-opacity="0"/></radialGradient></defs>'
  bg='<rect width="1200" height="900" fill="url(#sky)"/>'
  if theme=='forest':
   bg+='<path d="M0 550 Q300 390 650 570 T1200 510 V900 H0Z" fill="#a5c59b"/><path d="M0 702 Q300 553 650 711 T1200 680 V900 H0Z" fill="#86b18b"/>'
   for x,y,s in [(45,310,1.1),(220,233,.8),(1100,280,1.2)]:bg+=f'<g transform="translate({x} {y}) scale({s})"><path d="M-14 0-30 500 35 500 18 0" fill="#a68a68"/><ellipse cy="-7" rx="144" ry="134" fill="#79a182"/><ellipse cx="-71" cy="57" rx="104" ry="87" fill="#8eb48b"/></g>'
  elif theme=='space':
   for k in range(38):
    x=(k*157+83)%1200;y=(k*89+33)%570;bg+=f'<circle cx="{x}" cy="{y}" r="{2+k%3}" fill="#fff2c9" opacity=".8"/>'
   bg+='<ellipse cx="1000" cy="185" rx="96" ry="90" fill="#dfc4a5"/><ellipse cx="1000" cy="185" rx="148" ry="25" transform="rotate(-18 1000 185)" fill="none" stroke="#c6bfba" stroke-width="12"/><path d="M0 688 Q340 540 700 685 T1200 675 V900 H0Z" fill="#b5b6c9"/>'
  else:
   for x in [180,460,800]:bg+=f'<path d="M{x} 0 {x+45} 0 {x+290} 680 {x+100} 680Z" fill="#ebfff2" opacity=".12"/>'
   bg+='<path d="M0 708 Q330 590 700 718 T1200 685 V900 H0Z" fill="#accfc0"/>'
   for x in [80,1130]:bg+=f'<path d="M{x} 850 Q{x-65} 760 {x-25} 620 M{x} 850 Q{x+70} 730 {x+35} 570 M{x} 850 V620" stroke="#639c91" stroke-width="22" fill="none" stroke-linecap="round"/>'
   for k in range(13):bg+=f'<circle cx="{(k*183+101)%1200}" cy="{(k*83+91)%650}" r="{5+k%9}" fill="none" stroke="#ddf4e9" opacity=".5" stroke-width="3"/>'
  content=''
  if i==0:
   content=home(theme,60,430)+fox(610,445,1.18,'listen')+f'<circle cx="920" cy="680" r="120" fill="url(#glow)"/><path d="M897 662 Q911 635 941 655 L942 695 Q918 718 894 692Z" fill="#f7df8a" stroke="#d7b96f" stroke-width="4"/>'+paper(810,746,.5)
  elif i==1:
   content='<path d="M440 900 Q730 650 1130 670" fill="none" stroke="#e1d2aa" stroke-width="135"/>'+fox(385,438,1.1,'point')+friend(theme,835,580,1.55)+paper(677,700,1.3)
  elif i==2:
   content='<path d="M0 625 Q400 545 680 670 T1200 610 V740 Q800 800 380 697 T0 770Z" fill="#81b7b5"/><path d="M645 646 785 614 782 664 635 695Z M848 602 1075 574 1090 625 858 652Z" fill="#cfb383"/><circle cx="668" cy="692" r="16" fill="#6c9c99"/>'+fox(325,445,1.12,'listen')+friend(theme,535,705,1.1)
  elif i==3:
   content=mentor(theme)+fox(332,462,1.05,'point')+friend(theme,570,688,1.15)+paper(521,760,1.25)
  elif i==4:
   content='<path d="M185 775 Q615 585 1080 735" stroke="#ddcda3" stroke-width="130" fill="none"/>'+paper(491,658,1.5)+fox(315,402,1.28,'write')+friend(theme,849,654,1.6)+'<path d="M772 780 810 766 M878 743 917 731 M993 712 1037 703" stroke="#ae8c62" stroke-width="8" stroke-linecap="round"/><circle cx="925" cy="555" r="110" fill="url(#glow)"/><path d="M913 532 H942 V568 Q927 591 913 568Z" fill="#ffe4a0"/>'
  else:
   content=home(theme,830,480)+fox(410,495,.9,'wave')+friend(theme,637,686,1)+paper(165,694,.8)+'<circle cx="312" cy="190" r="55" fill="#fff0b3"/>'
   for k in range(9):content+=f'<circle cx="{110+k*122}" cy="{310+(k%3)*37}" r="5" fill="#fff3ac"/>'
  svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 900" role="img"><title>{escape(names[i])}：{theme}主题本地示例分镜</title>{defs}{bg}{content}<rect x="18" y="18" width="1164" height="864" rx="35" fill="none" stroke="#fff7e3" stroke-opacity=".35" stroke-width="3"/></svg>'
  (out/f'{theme}-{i+1:02}.svg').write_text(svg,encoding='utf-8')
