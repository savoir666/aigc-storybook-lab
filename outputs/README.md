# 多模态产物与案例

|案例|故事JSON|绘本PDF|有声书MP3|故事视频MP4|
|---|---|---|---|---|
|会发光的种子（森林）|[JSON](final-cases/forest-final-20261028/project.json)|[PDF](final-cases/forest-final-20261028/storybook.pdf)|[MP3](final-cases/forest-final-20261028/story-audio.mp3)|[MP4](final-cases/forest-final-20261028/story-video.mp4)|
|小橘的珊瑚湾奇遇（海洋）|[JSON](final-cases/ocean-final-20261028/project.json)|[PDF](final-cases/ocean-final-20261028/storybook.pdf)|[MP3](final-cases/ocean-final-20261028/story-audio.mp3)|[MP4](final-cases/ocean-final-20261028/story-video.mp4)|

每个案例包含6幅真实API PNG及逐图proof、实际输入case-input.json、模型请求prompt-record.json、Agent轨迹、音视频证明、最终哈希清单。森林另含真实人类合作结尾干预及修订记录。媒体文件较大，GitHub若不内联播放，可点击下载后本机打开。

森林：4种音色、414.264秒音频、约414.26秒视频、108条字幕；海洋：4种音色、419.04秒音视频、107条字幕。两本均8页。55个清单文件复制后逐项校验，原始证明保持不变。

三种Prompt的真实对照与示例：[原始输出](prompt-comparison/prompt-comparison.json)，[报告](../docs/prompt-quality-analysis.md)。

在主应用中查看这些已生成作品：先运行`python scripts/restore_sample_cases.py`，再启动本机服务，打开作品书架。恢复只复制本地样本，不会调用模型；重复执行时保留已有同名项目，不覆盖修改过的文件。

第一周本人网页操作录屏独立提交，与本目录故事成片分别归档。
