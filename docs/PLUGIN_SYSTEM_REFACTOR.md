# 插件系统与数据目录改造总结

## 改造目标

1. **统一数据目录**: 默认使用 `data/` 作为项目数据根目录
2. **插件目录结构化**:
   - `data/plugins/installed/` - 插件代码
   - `data/plugins/plugins_config/` - 插件配置
   - `data/plugins/plugins_data/` - 插件持久化数据
3. **插件元数据标准化**: 添加 `metadata.json` 支持
4. **向后兼容**: 自动从旧路径迁移数据

## 目录结构

### 新版本 (data 目录结构)

```
项目根目录/
├── data/                              # 统一数据目录
│   ├── config.json                    # 主配置文件
│   ├── chat_history.json             # 聊天记录
│   ├── plugins/                       # 插件根目录
│   │   ├── installed/                 # 插件代码目录
│   │   │   ├── example_plugin.py
│   │   │   └── live2d_plugin/
│   │   │       ├── __init__.py
│   │   │       ├── metadata.json      # 插件元数据
│   │   │       └── ...
│   │   ├── plugins_config/            # 插件配置目录
│   │   │   ├── example_plugin.json
│   │   │   └── live2d_plugin.json
│   │   └── plugins_data/              # 插件持久化数据目录
│   │       ├── example_plugin/
│   │       └── live2d_plugin/
│   ├── temp/                          # 临时文件
│   │   ├── images/
│   │   └── screenshots/
│   └── logs/                          # 日志文件
```

### 旧版本路径

- 配置文件:
  - Windows: `%APPDATA%/AstrBotDesktopClient/config.json`
  - macOS: `~/Library/Application Support/AstrBotDesktopClient/config.json`
  - Linux: `~/.config/astrbot-desktop-client/config.json`
- 临时文件: `项目根/temp/`
- 插件: `desktop_client/plugins/installed/`, `desktop_client/plugins/configs/`

## 核心模块

### 1. data_manager.py

**职责**: 数据目录结构管理与旧数据迁移

**关键类**:
- `DataManager`: 数据目录管理器
  - `data_dir`: 数据根目录
  - `plugins_installed_dir`: 插件代码目录
  - `plugins_config_dir`: 插件配置目录
  - `plugins_data_dir`: 插件数据目录
  - `ensure_structure()`: 确保目录结构完整
  - `migrate_from_legacy()`: 从旧版本迁移数据

**全局函数**:
- `get_data_manager()`: 获取单例管理器
- `init_data_structure()`: 初始化数据目录并执行迁移

### 2. 插件元数据扩展 (base.py)

**新增字段**:
```python
@dataclass
class PluginMetadata:
    # 原有字段...
    entry_point: str = "__init__.py"       # 插件入口文件
    plugin_class: str = ""                 # 插件主类名称
    license: str = ""                      # 开源许可证
    config_schema: Dict[str, Any] = {}     # 配置项模式
```

**新增方法**:
```python
@classmethod
def from_json_file(cls, file_path: Path) -> "PluginMetadata":
    """从 metadata.json 文件加载元数据"""
```

### 3. 配置管理改造 (config.py)

**全局开关**:
```python
_use_data_dir: bool = True  # 是否使用新的 data 目录结构
```

**修改的方法**:
- `ClientConfig.get_config_dir()`: 支持 data 目录
- `ClientConfig.get_config_path()`: 支持 data 目录
- `StorageConfig.resolved_image_save_path`: 默认使用 `data/temp/images`
- `StorageConfig.resolved_chat_history_path`: 默认使用 `data/chat_history.json`

### 4. 插件管理器改造 (manager.py)

**构造函数参数**:
```python
def __init__(
    self,
    plugins_dir: Optional[str] = None,    # 插件代码目录
    config_dir: Optional[str] = None,     # 插件配置目录
    data_dir: Optional[str] = None,       # 插件数据目录(新增)
):
```

**新增属性和方法**:
```python
@property
def data_dir(self) -> Path:
    """获取插件数据根目录"""

def get_plugin_data_dir(self, plugin_name: str) -> Path:
    """获取指定插件的数据目录"""
```

### 5. 启动流程集成

**main.py**:
```python
from desktop_client.data_manager import init_data_structure

# 初始化数据目录结构并自动迁移旧数据
init_data_structure(auto_migrate=True)
```

**app.py**:
```python
def main():
    from .data_manager import init_data_structure
    init_data_structure(auto_migrate=True)
    # ...
```

## 迁移策略

### 自动迁移条件

1. **触发时机**: 应用启动时自动执行
2. **迁移标记**: `data/.migrated` 文件,避免重复迁移
3. **用户自定义路径**: 如果用户自定义了数据路径,不执行迁移

### 迁移内容

| 旧路径 | 新路径 | 迁移方式 |
|--------|--------|----------|
| `{平台配置目录}/config.json` | `data/config.json` | 复制 |
| `{平台配置目录}/chat_history.json` | `data/chat_history.json` | 复制 |
| `temp/*` | `data/temp/*` | 递归复制 |
| `desktop_client/plugins/installed/*` | `data/plugins/installed/*` | 递归复制 |
| `desktop_client/plugins/configs/*` | `data/plugins/plugins_config/*` | 复制 |

### 迁移安全性

- ✅ 只复制不删除,保留原数据
- ✅ 迁移失败不影响启动
- ✅ 记录详细日志
- ✅ 创建迁移标记避免重复

## 插件开发指南

### metadata.json 示例

```json
{
  "name": "live2d_plugin",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "Live2D 虚拟形象插件",
  "homepage": "https://github.com/...",
  "license": "MIT",
  "entry_point": "__init__.py",
  "plugin_class": "Live2DPlugin",
  "dependencies": ["PySide6>=6.5.0"],
  "min_app_version": "1.0.0",
  "tags": ["ui", "avatar", "live2d"],
  "config_schema": {
    "model_path": {
      "type": "string",
      "default": "",
      "description": "Live2D 模型文件路径"
    },
    "scale": {
      "type": "float",
      "default": 1.0,
      "description": "模型缩放比例"
    }
  }
}
```

### 插件目录结构

#### 单文件插件
```
data/plugins/installed/
└── my_plugin.py          # 插件代码
```

#### 目录插件
```
data/plugins/installed/my_plugin/
├── __init__.py           # 插件入口
├── metadata.json         # 元数据(可选,推荐)
├── widget.py             # 其他模块
└── resources/            # 资源文件
```

### 插件数据存储

```python
class MyPlugin(IPlugin):
    def on_load(self) -> bool:
        # 获取插件专属数据目录
        data_dir = self._manager.get_plugin_data_dir(self.name)

        # 保存数据
        data_file = data_dir / "my_data.json"
        with open(data_file, "w") as f:
            json.dump({"key": "value"}, f)

        return True
```

## 向后兼容性

### 开关控制

可通过修改 `config.py` 中的 `_use_data_dir` 切换新旧目录:
```python
_use_data_dir: bool = False  # 使用旧路径
```

### 旧版本插件兼容

- ✅ 不使用 metadata.json 的插件仍可正常加载
- ✅ metadata 从插件类的 `metadata` 属性获取
- ✅ 插件代码无需修改

## 测试建议

### 功能测试

1. **全新安装测试**:
   - 删除所有旧配置
   - 启动应用
   - 验证 `data/` 目录结构创建正确

2. **迁移测试**:
   - 准备旧版本配置和数据
   - 启动应用
   - 验证数据迁移完整性
   - 验证 `.migrated` 标记创建

3. **插件加载测试**:
   - 创建带 metadata.json 的插件
   - 创建不带 metadata.json 的插件
   - 验证两种插件都能正常加载

4. **路径切换测试**:
   - 测试 `_use_data_dir = True/False` 两种模式
   - 验证路径切换不影响功能

### 边界测试

- 配置文件不存在
- 迁移失败(权限问题)
- 插件目录不存在
- metadata.json 格式错误

## 文件清单

### 新增文件

- [desktop_client/data_manager.py](desktop_client/data_manager.py) - 数据目录管理器
- [desktop_client/plugins/example_plugin_metadata.json](desktop_client/plugins/example_plugin_metadata.json) - 示例插件元数据

### 修改文件

- [desktop_client/plugins/base.py](desktop_client/plugins/base.py:73-80,113-126) - 扩展元数据字段
- [desktop_client/config.py](desktop_client/config.py:15,332-355,212-252) - 集成 data_manager
- [desktop_client/plugins/manager.py](desktop_client/plugins/manager.py:93-155,159-193) - 适配新目录结构
- [desktop_client/main.py](desktop_client/main.py:34-37) - 初始化数据目录
- [desktop_client/app.py](desktop_client/app.py:796-799) - 初始化数据目录

## 已知限制

1. **迁移是单向的**: 从旧版本迁移到新版本后,无法自动回退
2. **路径硬编码**: plugins 目录名称固定为 "plugins"
3. **metadata.json 非强制**: 为保持兼容性,未强制要求 metadata 文件

## 后续优化建议

1. **元数据验证**: 添加 metadata.json schema 验证
2. **插件市场**: 基于 metadata 实现插件市场功能
3. **配置 UI**: 根据 config_schema 自动生成配置界面
4. **迁移向导**: 提供图形化迁移向导,增强用户体验
5. **备份机制**: 迁移前自动备份旧数据
