> 提交整理于2026-10-29。本文保留实际实验时间和局限；当前终版与提交状态以 [前八周交付索引](course-submission.md) 为准，历史实验与终版分别标注。

# 素材检索：细节查询补充实验

2026-10-28，实测本地TF-IDF与ONNX CLIP；预先指定目标素材，属于小样本自检。

| 查询 | 预期模板 | 实际Top3 | 预期排名 |
|---|---|---|---|
|雨打湿了没有地址的信，寻找等待来信的朋友|template-forest-02|template-forest-02、template-space-01、template-forest-01|1|
|月亮收不到晚安信，用纸火箭修复星际邮路|template-space-01|template-space-01、template-forest-04、template-space-03|1|
|把漂亮贝壳留给寄居蟹，只拍照片保护海洋|template-ocean-04|template-ocean-04、template-ocean-02、template-ocean-01|1|

模板正文索引现包括premise、characters、outline、age_range，能使用具体剧情检索。逐项图片/音效排名、分数、CLIP词典映射及未识别中文、结构化推荐保存在[原始结果](evidence/retrieval-detail-20261028.json)。

图片确实由CLIP编码器计算，但“邮路”“寄居蟹”等细节未必被中文有限词典识别，不能把模板命中当作图片细节理解。素材库24图为程序插画；本评估也不证明开放域表现。跨模态分数未校准，实际使用应按类型分别查看。
