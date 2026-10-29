# 前八周交付索引

2026-10-29整理。技术成果与个人学习记录分开；本人已确认个人反思并反馈两套成品无问题，现场答辩和课程平台提交仍待完成。

|周次|代码与成品|报告、证明与日志|
|---|---|---|
|1|[Trae网页](../web/trae-story.html)、[使用说明](../使用说明.md)；本人视频117.87秒另行提交|[作业0日志](ai-logs/assignment-0.md)、[AI协作总表](../ai_log.md)|
|2|`src/storybook/story.py`、`providers.py`；[三策略真实输出](../outputs/prompt-comparison/prompt-comparison.json)|[质量对比表](prompt-quality-analysis.md)、[作业1日志](ai-logs/assignment-1.md)|
|3|[两套最终作品](../outputs/README.md)：每套6张API图、1本PDF|[一致性方案与对比图](character-consistency.md)、[作业2日志](ai-logs/assignment-2.md)|
|4|最终作品内`story-audio.mp3`，4种音色，414.264/419.04秒；主应用同步高亮|[音色及参数表](voice-design.md)、[作业3日志](ai-logs/assignment-3.md)|
|5|最终作品内`story-video.mp4`，两套均超过60秒，配音/BGM/字幕|[剪辑流程](audio-video-pipeline.md)、[作业4日志](ai-logs/assignment-4.md)|
|6|12模板/24图/6音效；文本TF-IDF+实际ONNX CLIP；`scripts/setup_clip.py`|[构建与评估](week06_retrieval_evaluation.md)、[细节查询评估](retrieval-detail-evaluation.md)、[作业5日志](ai-logs/assignment-5.md)|
|7|LangChain模型规划、四核心工具、两个最终案例与用户干预|[Agent架构](week07_agent_architecture.md)、两案例`agent_trace.md`、[作业6日志](ai-logs/assignment-6.md)|
|8|本机可运行的图文音视频、素材库和Agent|[系统架构](architecture.md)、[现场讲解提纲](defense-guide.md)、[本人准备指南](student-confirmation.md)|

## 当前仍需本人完成

1. 保留GitHub上传完成后的截图（至少能看见仓库名、文件列表和README）。
2. 查明老师指定的课程提交入口；如发Classroom邀请，按邀请提交仓库与附件。目前公开仓库不等于已交到课程平台。
3. 第8周本人完成8—10分钟现场运行与答辩，不能只放第一周录屏。

## 本人已确认

本人已确认[个人反思](ai-logs/student-reflection.md)，并对森林、海洋两套成品反馈“没问题”。用时仍为“未记录”；本次反馈不额外换算观看时长或细项评分。

## 技术边界

第1周Trae页面使用模板与18幅本地SVG，不作为第3周API图片证据；两套终版在outputs/final-cases中。CLIP权重不进Git，按复现说明安装；CLIP与标签降级的引擎状态分别标注。TTS情绪是韵律参数调节，不宣称原生情感风格。固定Seed和固定描述不能保证逐像素相同。

Git历史从2026-10-29真实提交开始，不倒填课程周次；前期开发经历以有证据的日志归档。
