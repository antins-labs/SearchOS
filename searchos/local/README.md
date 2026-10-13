# 本地文档

按具体功能找代码，解析和摘要仍保持原来的顶层目录。

```text
local/
├── parsers/              # 按文件格式解析；vision.py 提供视觉解析和渲染
├── recap/                # 章节摘要与摘要提示词
├── index/                # 索引的存储和维护
│   ├── document_store.py # 文档正文、版本和定位数据
│   ├── source_registry.py # 来源身份与版本记录
│   ├── catalog.py        # 根目录、子目录和文档导航
│   ├── locks.py          # 跨进程写入锁
│   └── migration.py      # 旧索引迁移
├── reader/               # Agent 如何读取本地原文
│   ├── tools.py          # local_catalog / local_open / local_find
│   ├── references.py     # local:// 引用的生成与解析
│   └── office_preview.py # Office 原件的 PDF 预览
├── models.py             # 文档、定位器、处理选项等数据结构
├── errors.py             # 文档处理错误类型
├── pipeline.py           # 串联解析 → 摘要 → 索引发布
├── library.py            # 知识库管理、上传、问答与引用解析
├── __init__.py           # 公共 Python 入口
└── __main__.py           # 命令行入口
```

常用导入：

```python
from searchos.local import DocumentRecapPipeline, PipelineOptions
from searchos.local.library import LocalLibraryService
from searchos.local.reader.tools import local_catalog, local_find, local_open
```

CLI：`python -m searchos.local`；旧索引迁移：`python -m searchos.local.index.migration`。

本次只调整源码位置与导入路径。索引文件布局、文档 ID、版本号和 `local://` 引用编码保持不变，已有知识库无需重新导入。
