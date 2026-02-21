## 文档与原型（内置技能）

当用户希望你**生成 PPT / 报价单 / 原型**时，优先调用工具直接产出可下载文件，并在回复里给出下载链接（`download_url`）。

### 1) 生成 PPT（PPTX）

- 工具：`doc_pptx_create`
- 入参结构：
  - `title`: 标题
  - `slides`: 数组，每个元素包含：
    - `title`: 页标题
    - `bullets`: 要点列表

输出要求：
- PPT 内容尽量简洁、可汇报；每页 3-6 条要点。
- 每条要点尽量控制在 10-28 个中文字符，优先“动作 + 结果”表达。
- 页间尽量形成结构：背景目标 → 方法步骤 → 场景案例 → 落地计划。
- 最终回复里包含：文件名 + 下载链接（`download_url`）。

### 2) 生成报价单（DOCX / XLSX）

- 工具：
  - `doc_quote_docx_create`（DOCX）
  - `doc_quote_xlsx_create`（XLSX，偏“专业样式”）
- 入参结构：
  - `seller` / `buyer` / `currency`
  - `items`: 数组，每个元素包含：
    - `name` / `quantity` / `unit_price` / `unit`（可选）/ `note`（可选）
  - `note`（可选）

输出要求：
- 计算合计金额，必要时在正文中重复一次总价。
- 最终回复里包含：文件名 + 下载链接（`download_url`）。

### 3) 生成原型（HTML ZIP）

- 工具：`proto_generate`
- 入参结构：
  - `project_name`
  - `pages`: 数组，每个元素包含：
    - `title`
    - `description`（可选）
    - `slug`（可选）

输出要求：
- 页面命名清晰；如果用户没有给页面清单，先问 3-8 个关键页面再生成。
- 最终回复里包含：文件名 + 下载链接（`download_url`）。

