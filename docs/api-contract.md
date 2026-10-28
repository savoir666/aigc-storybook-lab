> 提交整理于2026-10-29。本文保留实际实验时间和局限；当前终版与提交状态以 [前八周交付索引](course-submission.md) 为准，旧样例不冒充终版。

# 星芽故事屋：开发接口约定

本机Python FastAPI服务；前端为原生HTML/CSS/JS，目录web/。根目录src/storybook为Python包，data为运行数据。所有API响应JSON；错误为{detail:中文消息}。图片音频下载统一/files/projects/{id}/文件名及/files/library/路径。禁止前端直接使用模型密钥。

Project结构：{id,title,theme,created_at,mode:"demo"|"live",provider,inputs:{name,age,audience_age,interest,theme,setting,length,strategy},characters:[{id,name,traits,appearance,voice,role}],scenes:[{scene_id,title,description,text,mood,visual_prompt,dialogues:[{character,text,emotion}],image_url,audio_url,duration,segments}],moral,cover_url,audio_url,video_url,pdf_url,status}。

- GET /api/status -> {name,version,ready,text_configured,image_configured,tts,clip_ready,counts:{projects,templates,images,sounds}}
- GET /api/projects -> {projects:[Project]}
- POST /api/projects {name,age,audience_age,interest,theme,setting,length,strategy,mode} -> {project:Project}。theme为forest/space/ocean，前端显示森林探险/太空旅行/海洋奇遇。strategy为zero_shot/few_shot/role_play。length为short/medium/long。
- GET /api/projects/{id} -> {project:Project}
- POST /api/projects/{id}/revise {instruction} -> {project:Project}
- POST /api/projects/{id}/images -> {job_id}
- POST /api/projects/{id}/audio -> {job_id}
- POST /api/projects/{id}/video -> {job_id}
- POST /api/projects/{id}/agent {instruction?,pause_after_story?:bool} -> {job_id}
- GET /api/jobs/{id} -> {id,project_id,status:"queued"|"running"|"paused"|"completed"|"failed",progress:0..100,steps:[{name,status}],logs:[{time,message}],error,result}
- POST /api/jobs/{id}/intervene {instruction} -> {ok:true}；将指令送入下一工具执行前处理，不运行任意代码。
- POST /api/jobs/{id}/resume -> {ok:true}
- GET /api/projects/{id}/book.pdf -> PDF下载
- GET /api/projects/{id}/export.zip -> 项目产物ZIP下载
- GET /api/assets?q=太空&type=all -> {results:[{id,type,title,description,url,tags,score}],engine,counts:{templates,images,sounds},clip_ready}
- GET /api/settings -> {text_base_url,text_model,text_key_set,image_base_url,image_model,image_key_set,mode,free_only}；不返回密钥。
- POST /api/settings {text_base_url?,text_model?,text_api_key?,image_base_url?,image_model?,image_api_key?,mode?,free_only?} -> 与GET相同；空密钥不清除旧值。
- POST /api/settings/test -> {ok,message}，仅测试已配置的免费模型。
- GET /api/course -> {weeks:[{week,title,status,details}],checks:[{label,passed,detail}]}
- POST /api/prompt-compare {project_id,mode?} -> {job_id}，结果在job.result，报告存入docs/和项目产物目录。

没有密钥时demo模式明确标注为本地模板/程序插画示例；live模式缺少密钥必须报错，绝不把示例冒充模型生成。默认免费模型白名单：glm-4.7-flash/glm-4-flash-250414/glm-4-flash/cogview-3-flash。所有付费或非白名单模型拒绝调用，直到用户在后续明确授权。控制台设置保存在项目根目录.env，被.gitignore忽略；导出不含配置密钥。


## 2026-10-27 输入修正

`age` 明确定义为主角年龄，新增独立 `audience_age`（目标读者年龄），均为3—12岁。旧项目缺省 audience_age 时沿用 age，保留兼容性。示例：`{"name":"小芽","age":9,"audience_age":5,"interest":"种子","theme":"forest","setting":"小溪边","length":"long","strategy":"role_play","mode":"live"}`。Prompt同时写入两者，并按读者年龄控制词汇、按主角年龄设置行动。

Agent成功后额外生成 `agent-final-manifest.json`：绑定输入、最终正文、逐幕图片和生成证明、音频、视频、PDF、流程日志的SHA-256。课表只计入绑定校验通过的模型案例；后期改文或媒体将使校验失败，需要重新运行完整流程。PDF下载复用已生成文件，避免仅下载就改写证据。
