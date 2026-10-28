> 提交整理于2026-10-29。本文保留实际实验时间和局限；当前终版与提交状态以 [前八周交付索引](course-submission.md) 为准，历史实验与终版分别标注。

# 第6周：素材库、真实向量检索与实测评估

## 实现与数据来源

本地素材清单为 `data/library/manifest.json`：12个故事模板、24张1200×900 PNG插画、6种WAV音效。插画由Pillow程序绘制，音效由程序合成，均在素材元数据中注明来源；这些素材不是AI模型生成的成果。

文本模板与音效描述采用 scikit-learn `TfidfVectorizer` 的中文字符1—3元组、子线性词频和L2归一化，使用向量内积进行余弦检索。图片采用 **实际ONNX CLIP图文检索**：文字输入和PNG像素分别经CLIP编码器获得512维向量，再计算余弦相似度。图片排名没有使用标题或标签分数替代CLIP。

模型为 [Xenova/clip-vit-base-patch32](https://huggingface.co/Xenova/clip-vit-base-patch32)，固定revision `4c1807b705b1d015fb032789cc4d221b23025a6f`。两个量化编码器分别约64.5 MB和89.1 MB，通过ONNX Runtime CPU执行，未依赖PyTorch。`data/models/clip/download_manifest.json`记录原始下载来源、SHA256和 `verified_cpu_embeddings: true`；安装脚本实际验证了图文两编码器均返回512维向量。

该模型使用英文文本编码器。中文查询先经代码中公开的有限主题词典映射，例如“太空火箭”映射为 `outer space, rocket`。API返回映射文本及未识别中文，不能将此称为通用中文机器翻译或中文CLIP。缺少模型或依赖时，`clip_ready=false`，响应和每条图片结果明确注明“标签文本向量降级，非CLIP”。

## 2026-10-25实际查询结果

使用 `AssetSearch(root).search(query, limit=5)` 查询全部素材。完整原始响应保存在 `docs/retrieval_evaluation.json`。三个查询均返回 `clip_ready=true`、空警告和 `image_errors=[]`；下列图片得分全部来自真实ONNX CLIP图文余弦计算。

| 自然语言查询 | 显式英文词典映射 | Top1图片 | 标题 | 余弦分数 | Top5主题一致项 |
|---|---|---|---|---:|---:|
| 森林友谊 | forest, friendship | image-forest-06 | 口袋里的种子 | 0.305021 | 5/5 |
| 太空火箭 | outer space, rocket | image-space-04 | 机器人也会想家 | 0.307698 | 5/5 |
| 海底珊瑚 | underwater, coral reef | image-ocean-06 | 勇敢的小小信使 | 0.281465 | 5/5 |

“主题一致项”按素材清单的forest/space/ocean主题标签核查，仅评估这三个查询与粗粒度场景的匹配。结果支持系统能够区分本库的三个主题，不能据此证明细节级语义理解、开放域检索性能或普遍100%准确率。例如“海底珊瑚”的Top1不是标题为“珊瑚花园”的图片，说明视觉相似度排序与标题精确匹配不同。

## 输出与使用

`GET /api/assets?q=太空火箭&type=image`返回素材ID、类型、标题、说明、URL、标签、分数和使用的引擎；支持 `all/template/image/sound` 过滤。额外的 `generation_suggestions` 按类型提供推荐模板、图片、音效ID和可用于生成的视觉提示词，供后续创作上下文使用。引用已有素材时应保留其来源说明。

## 已验证与限制

- 主进程对 `tests/test_retrieval_agent.py tests/test_media.py` 联合实跑：`19 passed in 7.65s`，包含全部13项检索/Agent测试。覆盖中文向量排序、模态筛选、空查询、限制条数、缺少CLIP时的明确降级、素材路径越界拒绝、工具白名单及依赖校验，以及异步执行与用户干预。
- 本次实际对24张PNG进行了CLIP编码；同一进程中按图片修改时间和大小缓存，重启后重新计算。
- TF-IDF对模板/音效进行文本描述检索，不是对WAV声学内容的相似度检索。
- 不同引擎的原始余弦分数尚未统一校准，跨类型排名应结合模态过滤使用；余弦分数不是概率。
- 当前仅有3个测试查询和42个素材，不包含独立盲评、长尾查询集或大规模性能测试；有限中文词典未覆盖的内容可能检索不准。


## 2026-10-28当前修订

已补三组具体剧情查询：无地址雨湿来信、月亮晚安信纸火箭、寄居蟹贝壳留存。目标模板均Top1，具体词典未识别内容和CLIP图片排名完整保留，见retrieval-detail-evaluation.md。该结果不证明图片细节语义识别或开放域准确率。
