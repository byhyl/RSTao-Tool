# RSTao-Tool UI/UX、前端架构与数据管理流升级方案

## 审查范围

本次审查覆盖主入口、授权激活、主窗口、资源面板、各业务 Tab、项目保存/恢复、资源登记、结果历史、设置持久化、3D 工作台、打包与安装脚本。当前项目已经形成了清晰的三层基础：`core/` 负责算法与资源解析，`data/` 负责影像/矢量 I/O，`ui/` 负责 CustomTkinter 桌面界面；项目文件通过 `ProjectManager` 保存 Tab 状态、资源、数据源和结果历史。

## 当前体验诊断

1. 导航模型仍偏菜单化。主功能入口藏在顶部菜单，左侧资源面板承担了导入、预览、定位、移除，但缺少明确的工作区导航与流程状态，用户需要记住“某类数据应该进入哪个 Tab”。
2. 欢迎页更像启动页而不是工作台入口。它能新建/打开项目，但没有把“最近项目、最近资源、上次任务、快速导入”组合成可继续工作的上下文。
3. 各 Tab 自成体系，控件密度、按钮语义、状态反馈不完全一致。部分操作用状态栏提示，部分用弹窗，后台任务进度和取消能力也不统一。
4. 项目资源与业务状态存在重复记录。`resources`、`data_sources`、各 Tab 的路径字段、`result_history` 都会记录同一份输入/输出信息，当前靠 helper 同步，后续功能变多后容易出现状态漂移。
5. 自动保存与恢复能力已有雏形，但用户可见性不足。状态栏显示保存状态，但缺少“保存中、已自动保存、恢复来源、冲突处理”的清晰提示。
6. 主题系统已集中在 `ui/theme.py`，但组件层级还没有形成稳定设计系统。按钮、卡片、树表、工具栏、任务面板、空状态、错误提示仍散在各模块。
7. 3D 能力已经从弹窗向集成 Tab 迁移，这是正确方向，但与资源面板、项目资源、任务历史之间还需要更强联动。

## 推荐目标体验

把应用升级为“项目驱动的遥感工作台”：用户打开项目后，第一眼看到当前项目、资源目录、主工作区、任务/结果状态；所有导入的数据先进入资源中心，再从资源中心分发到影像处理、匹配、矢量、坐标、检测、3D 等工作流。Tab 不再像孤立工具，而是共享同一份项目上下文。

建议主界面分为四个稳定区域：

1. 顶部应用栏：项目名、保存状态、全局搜索/命令入口、设置、授权/版本状态。
2. 左侧资源与工作流导航：资源树、筛选、导入、当前选中资源的可用动作。
3. 中央工作区：当前功能面板，保留专业操作密度，但统一标题、工具栏、参数区、预览区、输出区。
4. 底部任务与状态栏：坐标/缩放/图像信息、后台任务进度、最近结果入口、错误与警告聚合。

## 前端架构升级

### 1. 建立 UI Shell

新增一个 `ui/app_shell.py`，把主窗口拆成 Shell、Navigation、Workspace、StatusArea 四层。`MainWindow` 只负责生命周期、项目打开/关闭、全局命令注册，不再直接拼装全部菜单和面板。

建议接口：

```python
class AppShell(ctk.CTkFrame):
    def set_project(self, project_view_model): ...
    def set_active_panel(self, panel_id: str): ...
    def set_tasks(self, tasks: list[TaskViewModel]): ...
```

收益是界面骨架稳定，功能面板能迭代而不影响窗口生命周期。

### 2. 建立 Panel 注册表

当前 `init_panels()` 手动实例化全部 Tab。建议升级为 `PanelRegistry`：

```python
PanelSpec(
    id="image_processing",
    title="图像处理",
    icon="image",
    factory=ImageProcessingTab,
    supported_resource_types={"raster"},
)
```

资源面板双击资源时，可以根据资源类型展示“打开方式”，而不是硬编码 `_preview_raster()`、`_switch_vector()`。

### 3. 统一组件库

在 `ui/components/` 下沉淀通用组件：

- `ActionButton`、`IconButton`、`Toolbar`
- `Section`、`InspectorPanel`、`EmptyState`
- `TaskToast`、`ProgressOverlay`
- `ResourceTree`、`PropertyGrid`
- `ParameterForm`、`NumberField`、`PathPicker`

保留 CustomTkinter，但减少各 Tab 自己拼按钮和卡片的重复。现有 `ui/ui_helpers.py` 可以作为第一步迁移入口。

### 4. 统一反馈模型

把弹窗分级：

- 可恢复、非阻塞：状态栏/Toast。
- 会影响结果质量：面板内警告条。
- 会丢数据或不可逆：确认对话框。
- 异常失败：`show_actionable_error()`，必须带下一步建议和日志入口。

后台任务统一走 `TaskManager`，提供进度、取消、失败重试、完成后写入结果历史。

## 数据管理流升级

### 1. 项目模型分层

保留 `.rstao` JSON，但把项目状态拆成更明确的四层：

```text
project
├─ metadata: 项目名、版本、创建/修改时间
├─ resources: 文件资源、类型、hash、空间参考、可见性、标签
├─ workspace: 当前面板、布局、选中资源、视图状态
├─ operations: 任务历史、参数、输入、输出、指标、日志引用
└─ settings_snapshot: 与项目相关的默认参数
```

各 Tab 的私有状态不再保存完整业务事实，只保存视图状态和临时参数；输入/输出引用统一指向 `resource_id` 或 `operation_id`。

### 2. 资源成为单一事实源

目前 `record_data_source()` 同时写 `data_sources` 和 `resources`，各 Tab 还保留路径。建议：

- `resources` 作为唯一资源目录。
- `data_sources` 逐步迁移为 `resources` 的派生视图，或保留为兼容字段但不再由业务直接写入。
- 每个结果输出也登记为资源，带 `origin_operation_id`。
- 所有路径保存为绝对路径 + 可选项目相对路径，打开项目时做路径重定位检查。

### 3. 操作记录标准化

每次处理生成 `OperationRecord`：

```python
{
  "operation_id": "...",
  "type": "feature_detection",
  "inputs": ["resource_id"],
  "outputs": ["resource_id"],
  "params": {},
  "metrics": {},
  "status": "success|failed|cancelled",
  "started_at": "...",
  "finished_at": "..."
}
```

报告、结果历史、任务历史都从这里派生，减少重复数据。

### 4. 引入 ProjectStore

`ProjectManager` 现在同时负责 JSON 结构、最近项目、自动保存、资源增删、历史记录。建议拆为：

- `ProjectStore`：读写、迁移、自动保存、备份恢复。
- `ResourceRepository`：资源增删改查、hash、路径重定位。
- `OperationRepository`：任务/结果记录。
- `RecentProjectStore`：最近项目。

UI 只通过服务接口操作项目，不直接修改 `current_project` 字典。

## 分阶段路线

### 第一阶段：收敛体验和状态入口

1. 保持现有界面，先新增统一应用栏和左侧导航。
2. 把所有导入入口统一到资源中心，Tab 内加载文件后也自动登记资源。
3. 为资源属性、空间参考警告、路径失效增加面板内提示。
4. 后台任务统一显示在底部任务区。
5. 完成图标统一：窗口图标、exe 图标、安装包图标、快捷方式图标均使用 `assets/icon.ico`。

### 第二阶段：数据模型迁移

1. 增加 `schema_version = 5` 的迁移器。
2. 为现有 `resources`、`data_sources`、`result_history` 生成稳定 id。
3. 新增 `operations`，让新任务写入标准操作记录。
4. Tab 状态中的路径逐步替换为 `resource_id`。
5. 项目打开时做资源可用性扫描，提供批量重定位。

### 第三阶段：工作流化

1. 资源右键菜单根据类型显示可用工作流：影像处理、匹配、检测、矢量叠加、3D 加载。
2. 每个面板顶部显示输入资源、参数预设、输出位置。
3. 处理完成后自动形成结果资源和操作记录。
4. 报告生成从 `operations` 聚合，不再手动读取各 Tab 内部变量。

### 第四阶段：高级体验

1. 命令面板：搜索功能、资源、最近操作。
2. 参数预设库：全局默认 + 项目覆盖。
3. 可恢复任务队列：长任务失败后可重试。
4. 项目健康检查：缺失文件、空间参考冲突、输出路径不可写、依赖缺失。
5. 插件面板接入 Panel 注册表，让插件也能注册资源动作和工作流。

## 优先级建议

最高优先级是“资源单一事实源”和“任务记录标准化”。这两项会直接降低后续功能扩展成本，也能让 UI 从“工具集合”升级为“项目工作台”。视觉升级可以同步小步推进，但不建议先大改皮肤；应先稳定导航、状态、资源和任务流。

## 图标落地说明

已将运行时窗口图标、打包配置、安装器图标入口统一到 `assets/icon.ico`：

- 主窗口、激活窗口、管理端窗口调用共享图标 helper。
- `pyproject.toml` 保留 exe 图标配置，并声明将 ico 作为运行时数据文件。
- Inno Setup 设置安装包图标，并为开始菜单/桌面快捷方式显式指定图标。
- 开发打包命令补充 `--add-data "assets/icon.ico;assets"`，避免 exe 内能显示图标但运行时窗口找不到 ico。
