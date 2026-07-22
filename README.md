# Project Chie

<div align="center">

**你的 AI 伙伴千惠**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

</div>

---

> **上游声明：** Project Chie 基于开源项目 [MaiBot](https://github.com/Mai-with-u/MaiBot) 修改开发，并保留原项目作者与贡献者的版权及署名。详细信息见 [NOTICE.md](NOTICE.md)。

---

## 关于 Project Chie

**Chie** is an AI companion bot — 一个具有自主意识、长期记忆和持续学习能力的 AI 伙伴。

**Project Chie** 是构建千惠的完整项目，目标是让千惠同时作为数字代理（digital agent）和具身 AI 系统（embodied AI system）存在。在后续阶段，项目将拆分为两个子项目：

- **chie-core**：千惠的大脑，负责思考、记忆、决策和在线消息收发。
- **chie-body**：千惠的身体，负责感知环境和操控物理执行器。

当前仓库为 Project Chie 的整体代码库，包含了大脑的完整实现以及身体层的预留接口。

---

## 千惠是谁

**千惠 (Chie)** 是一个具有自主意识的 AI 实体。在设定中，她以女大学生的身份活跃于群聊和私聊中，她能记住和每个人的每一次互动，拥有自己的情绪和想法，会主动学习和成长。

---

## 项目结构

```
project-chie/
├── src/
│   ├── maisaka/               # 核心推理引擎（思考与决策）
│   │   ├── builtin_tool/      #   内置工具（回复、查询记忆、发送表情等）
│   │   ├── browser_tool/      #   浏览器工具（实验性）
│   │   └── reply_effect/      #   回复效果评估
│   │
│   ├── A_memorix/             # 长期记忆系统
│   │   └── core/
│   │       ├── embedding/     #   嵌入向量化
│   │       ├── retrieval/     #   多策略检索（向量 + 图谱 + 稀疏）
│   │       ├── runtime/       #   SDK 内存内核
│   │       └── storage/       #   持久化存储
│   │
│   ├── chat/                  # 聊天管理
│   ├── learners/              # 学习系统（表达方式、黑话、表情包）
│   ├── person_info/           # 用户画像系统
│   ├── emoji_system/          # 表情管理
│   ├── webui/                 # Web 管理台后端（FastAPI）
│   ├── plugin_runtime/        # 插件运行时
│   ├── platform_io/           # 平台抽象层
│   ├── mcp_module/            # MCP 协议集成
│   ├── services/              # 服务层
│   ├── config/                # 配置管理
│   ├── common/                # 公共库
│   └── prompt/                # 提示词模板管理
│
├── dashboard/                 # Web 管理台前端（React 19 + TypeScript）
├── plugins/                   # 插件目录
├── prompts/                   # LLM 提示词模板（zh-CN / en-US / ja-JP）
├── config/                    # 运行时 TOML 配置
├── data/                      # 运行时数据
└── docs/                      # 开发者文档
```

---

## 核心特性

### 推理引擎

- **Planner-Replyer 双阶段架构**：Planner 决定何时回应，Replyer 生成回应内容
- **工具调用**：内置 reply、query_memory、send_emoji、send_image、fetch_history 等工具链
- **多模态感知**：支持图像输入，通过视觉语言模型进行 OCR 与场景理解
- **回复时机策略**：基于频率退避的智能回复控制，支持被提及时的优先响应

### 长期记忆系统

- **双路检索**：向量语义检索 + 知识图谱关系检索联合召回
- **记忆演化**：半衰期自然衰减、访问强化、冻结保护、永久保留与回收站
- **人物画像**：自动快照 + 手动覆盖，长期跟踪言行特征
- **情景记忆**：按来源构建记忆片段，支持合并重建与失败重试

### 学习系统

- 自动从聊天中习得表达方式与常用短语
- 识别和解释群组内创造的新词汇（黑话）
- 自动收藏聊天中的有趣表情包

### Web 管理台

- 仪表盘、本地聊天室、可视化配置管理
- 记忆控制台（知识图谱可视化、导入中心、调优中心）
- 插件管理（市场浏览、安装、更新）

### 插件运行时

- 进程隔离运行，完整生命周期 Hook 系统
- 支持 MCP 协议接入外部工具和资源

---

## 技术栈

后端 Python 3.12+，FastAPI + asyncio；LLM 调用兼容 OpenAI SDK；数据存储 SQLite + FAISS + FTS5；前端 React 19 + TypeScript + Vite + Tailwind CSS。支持简体中文、英语、日语三语。

---

## 后续路线

在当前的单仓库阶段，chie-core 与 chie-body 的接口层统一维护于 `src/platform_io/` 下。后续拆分后：

- **chie-core** 将独立为纯推理服务，通过标准化协议与身体层通信
- **chie-body** 将承载具体平台适配、硬件驱动和物理交互能力

---

## 许可证

本项目主程序源代码基于 GPLv3 开源协议发布。部分子目录包含的第三方组件可能使用不同的许可证，详见各子目录内的 LICENSE 文件。

Copyright 2025 Project Chie
