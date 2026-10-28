# Trae开发与后续核验记录（2026-10-28）

用户实际打开Trae项目，按聊天给出的提示词操作Builder，并反馈创建了web/trae-story.html、trae-story.css、trae-story.js，同时提供成品页面截图。Codex已核对文件真实存在。没有看到完整Trae聊天或模型名称，不补造其内容；不将整个主项目说成Trae开发。

## 证据

- 用户打开Trae截图：[user-opened-trae.png](evidence/trae/user-opened-trae.png)。
- 用户提供的原始页面截图：[user-shared-page.png](evidence/trae/user-shared-page.png)。截图仅证明当时页面呈现。
- Trae初版文件保存在[evidence/trae/original-files/](evidence/trae/original-files/)，哈希见provenance.json。
- Codex真实浏览器检查[qa-report.json](evidence/trae/qa-report.json)：8/8通过；初次7/8的错误结果保存在qa-before-error-fix.json。
- 早期AI助理页面操作演示（历史核验视频，本次不随代码提交）：由AI助理实际操作Chrome录制，静音附说明；不是用户操作录屏，也不是Trae开发过程录屏或第8周现场答辩。

## Codex后续修复

1. 后端所有长度均为6幕，去除初版“短3幕/中5幕”的不实承诺，改为正文长度。
2. 同一剧情text/dialogues只显示一份，避免重复。
3. 展示后端实际返回的每幕本地插图，失败时保留可读提示。
4. 阻止零岁、小数等非法年龄，不再自动把零岁改成6岁。
5. 展开后端422结构化错误，不再显示[object Object]。
6. 允许浏览器缩放，修复hidden显示语义；移除面向儿童页面中的接口实现术语。

## 实际检查范围

使用本机8766已运行服务，三个主题均真实POST mode=demo；主角7岁/读者5岁分别传入；逐幕翻页、键盘、防重复提交、空姓名/非法年龄、后端真实422及390px布局检查通过，无外部请求。这里的插图是程序示例图，不是新调用文生图模型。浏览器异常0项。

访问：http://127.0.0.1:8766/trae-story.html 。正确的本机启动文件为D:\AIGC作业\双击启动故事屋.cmd。入口是单向返回主应用，未新增主应用到此页的导航，不把双向互跳写成已实现。

个人总用时和AI辅助时间仍未记录，个人反思待本人填写；实际创建、原始文件和本次AI修复可分别核查。作者信息、远程仓库与现场展示仍待完成。

本次实际操作演示48.72秒，小于2分钟。旧提交包对照结果：{'web/index.html': True, 'web/app.js': True, 'src/storybook/server.py': True}；对照证据见main-files-baseline-check.json。这仅比较所列文件当前字节，不推断未记录的操作。

## 用户翻页反馈后的逐幕插画修改

用户实际反馈：“可以翻页，但是我觉得这个插图还可以改一下，我这个生成的插图每页都是一样的”。这证明本人已尝试阅读翻页并指出问题；不由此推算工时或代写个人学习心得。

原因：后端demo复用同主题素材，虽有小幅装饰/位置变化，但构图相似，不能满足逐幕阅读效果。Codex为Trae示例页新增18幅原生SVG本地分镜：发现、结伴、停下观察、请教、合作、回家；三个主题各6幅，固定小狐狸外观、大眼睛、围巾和背包，改变环境、伙伴、道具与手势。这是本地程序示例分镜，未调用文生图，不冒充真实AI插图，也不会根据任意自定义背景自动绘制新场景。

读者仅在mode=demo时按主题/幕次使用web/demo-scenes中的SVG；真实API作品继续使用原始image_url。主应用、后端和两套终版API作品没有被替换。重建源为scripts/build_demo_scene_assets.py（无模型调用）。

实际QA：8项交互检查再次通过；18/18插图在实际阅读器逐幕加载，每个主题6个不同URL和文件SHA，详见evidence/trae/scene-art-qa.json；三张six-scenes-*.png为真实浏览器渲染的全幕对照，Codex已目检。旧操作演示在previous-demo-before-scene-art.mp4保留供对照，当前演示同步更新。

插画修改后重新实际录制的页面演示为48.6秒，当前哈希见video-proof.json；旧48.72秒版本仅为历史对照。
