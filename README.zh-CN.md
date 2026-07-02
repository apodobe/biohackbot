# biohackbot

个人医疗语料库流水线：**安装 → 添加 PDF → 解析 →  enrichment**。

[English](README.md) · [Русский](README.ru.md) · [中文](README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> **非医疗建议。** 仅在本地整理您的文档，不提供诊断或处方。

---

## 1. 安装

```bash
git clone https://github.com/apodobe/biohackbot.git
cd biohackbot
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
medbots --help
```

## 2. 配置（首次）

在**私有**目录中存放数据（不要放在本公开仓库内）：

```bash
medbots init ~/my-health
```

目录结构：

```
~/my-health/
├── bot_config.json
├── sources/emias/      ← 放入 PDF
├── sources/medsi/
├── sources/gemotest/
├── sources/apple_health/   ← 可选：归档 export.zip
└── structured_database/
    ├── manifest.json
    ├── PATIENT_PROFILE.json   ← 填写出生日期
    ├── pdf_text/
    ├── doc_text/
    └── fitness/               ← Apple Health 导入结果
```

编辑 `PATIENT_PROFILE.json`：

```json
{"dob": "1985-03-20", "full_name_ru": "Your Name"}
```

## 3. 添加文档

将 EMIAS、Medsi 或 Gemotest 的化验 PDF 复制到对应的 `sources/` 子目录。

注册到 manifest：

```bash
medbots scan --bot-root ~/my-health
```

## 4. 解析 PDF

```bash
medbots extract-text --bot-root ~/my-health
medbots structure --bot-root ~/my-health
```

支持 **EMIAS**、**Medsi**、**Gemotest**（俄语检验单格式）。

### Apple Health（可选）

iPhone：健康 → 个人资料 → 导出所有健康数据 → `export.zip`

```bash
medbots import-apple-health --zip ~/Downloads/export.zip --bot-root ~/my-health --copy-zip
medbots validate-apple-health --corpus ~/my-health/structured_database
```

生成 `fitness/BODY_METRICS.json`、`WORKOUTS.json`、`APPLE_HEALTH_SUMMARY.md`。原始 `export.xml` **不保存**，仅聚合 JSON。

## 5.  enrichment

```bash
medbots pipeline --bot-root ~/my-health
medbots validate --corpus ~/my-health/structured_database
```

## 6. 可选：VPS（仅文本）

```bash
export VPS=root@YOUR_HOST
export CORPUS=~/my-health/structured_database
cd deploy && ./02-rsync-corpus.sh
```

详见 [deploy/RUNBOOK.md](deploy/RUNBOOK.md)。

---

## CLI

| 命令 | 说明 |
|------|------|
| `medbots init PATH` | 创建实例目录 |
| `medbots scan --bot-root PATH` | 扫描 `sources/` 注册 PDF |
| `medbots extract-text --bot-root PATH` | 提取 PDF 文本 |
| `medbots import-apple-health --zip FILE --bot-root PATH` | Apple Health → `fitness/` |
| `medbots structure --bot-root PATH` | 解析为结构化文档 |
| `medbots pipeline --bot-root PATH` | 规范化与索引 |
| `medbots validate --corpus PATH` | 完整性检查 |

## 隐私

个人健康数据请保存在本地或私有仓库，勿提交到本公开项目。见 [SECURITY.md](SECURITY.md)。

## 文档

- [语料库文件说明](docs/CORPUS.md)
- [License](LICENSE) — MIT, Copyright (c) 2026 Alexey Podobedov

**作者：** [Alexey Podobedov](https://github.com/apodobe)
