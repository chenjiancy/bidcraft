"""招标文件解析子系统（Task 8）。

模块划分：
- paths：项目数据目录解析（architecture.md 五，含路径逃逸防护）；
- preprocess：输入收集与 .doc → PDF 预处理（LibreOffice headless）；
- dedupe：同名多格式去重（docx > doc > pdf，同内容才去重）；
- engine：MinerU CLI 封装（文本/OCR 自动分流，输出 Markdown + JSON）；
- chapters：章节切分与子节结构（源文件噪声容错）；
- checkpoint：BP-1 长任务 Checkpoint（断点续跑、单项重试，供 Task 9-13 复用）；
- state：解析阶段状态机（UPLOADED→PARSING→PARSED，EM-5）；
- service：解析编排与 SSE 进度事件。
"""
