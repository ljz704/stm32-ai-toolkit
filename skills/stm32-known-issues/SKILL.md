---
name: stm32-known-issues
description: 记录一条踩坑/经验到 known_issues。当用户要求记录踩坑 记录经验 记一条 bug 教训，或提到 known_issues 踩坑记录 经验沉淀 时使用。逐项收集 现象/根因/修复/预防，去重后追加到记忆文件。
---

# 记录踩坑到 known_issues（DSH 版）

> 原 Claude Code 斜杠命令 `/newissue` 的 DSH skill 形式。

把一条踩坑记录写入工程记忆文件 `.dsh/memory/known_issues.md`（若目录下存在旧版
`.claude/memory/known_issues.md` 且 `.dsh/memory` 尚未建立，则写入旧路径并提示迁移）：

1. 逐项询问并收集：**现象**（出了什么问题）、**根因**（为什么）、**修复**（怎么解决的）、
   **预防**（如何避免再次发生）。用户已给出的信息直接采用，不要重复问。
2. 先读取记忆文件，检查是否已存在相同或相似问题；如已存在，提示用户去重
   （可询问是否追加补充信息而非新建条目）。
3. 按既有模板追加新条目，保持条目格式与现有内容一致，每条包含
   现象 / 根因 / 修复 / 预防 四个字段。
4. 写入成功后，展示新条目内容并确认已保存。

## 记忆文件路径
- 主路径：`.dsh/memory/known_issues.md`（DSH 风格）
- 兼容路径：`.claude/memory/known_issues.md`（旧版 Claude Code 工程遗留）
- 两个都存在时，以 `.dsh/memory/known_issues.md` 为准，并提示用户将旧文件内容合并/删除。
