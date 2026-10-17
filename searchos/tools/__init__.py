"""按能力组织 Agent 工具，每类目录在入口声明其工具集合。

schema：表格定义、行编辑与投影；tasks：任务、计划与报告；
socm_read：状态只读视图；writer：提纲与章节；skills：技能发现与执行；
python：受限代码执行；simple_browser：搜索与页面读取。

search_state 仅保存共享 ContextVar。Local Search 的文档工具由
searchos.local.reader.tools 提供，与本地资料库实现保持一致。
"""
