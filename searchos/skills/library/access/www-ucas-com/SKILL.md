---
name: www-ucas-com
description: Fetches UK university course details from UCAS, including course titles,
  providers,  qualifications, entry requirements, fees, and contact information.
metadata:
  searchos-category: access
  searchos-aliases: www_ucas_com
  searchos-config: '{"category": "access", "trigger": "", "availability": "enabled",
    "compatibility": ""}'
  host: www.ucas.com
compatibility: Python 3.10+；依赖见 requirements.txt；检索需要网络。
---

# www-ucas-com

Fetches UK university course details from UCAS, including course titles, providers,  qualifications, entry requirements, fees, and contact information.

## 调用

先定位本技能目录。脚本路径相对技能目录，输出路径相对调用者当前工作目录。脚本独立运行，不需要宿主框架。

```bash
python /path/to/www-ucas-com/scripts/run.py --help
python /path/to/www-ucas-com/scripts/run.py --params-file /path/to/parameters.json --result-file /path/to/result.json
```

参数可以用独立命令行选项（下划线转连字符）、`--params` JSON 或 `--params-file` 文件传入；文件名 `-` 表示读取 stdin。独立选项覆盖 JSON 同名值。以 [参数说明](references/parameters.json) 为准；缺省参数保留来源实现的默认行为。运行 `--validate-only` 可只校验参数，`--check-dependencies` 可检查 Python 依赖，两者均不执行检索。

阅读 [来源操作说明](references/source-guide.md) 选择功能、查询、分页和结束条件。原文中的函数调用仅描述参数语义；使用本页 CLI 执行。

## 环境与结果

依赖通过 `python -m pip install -r /path/to/www-ucas-com/requirements.txt` 安装，由调用者管理环境。

`--result-file` 保存完整 JSON；省略时输出到 stdout，诊断写 stderr。参数错误、依赖缺失、异常及来源声明失败使用非零退出码；空数组表示本次无命中，不能推断来源不存在相关记录。源码沿用原检索逻辑，公开接口和页面变化仍需实际核验。

结果保留来源返回的字段与链接，不补写虚构原文。缺少可核验正文时，继续读取结果中的原始 URL；普通结构化结果不自动成为来源证据。需要翻页时按来源游标继续调用。

