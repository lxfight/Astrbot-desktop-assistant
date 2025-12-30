"""
数据目录管理模块

统一管理项目的 data 目录结构:
- data/config.json - 主配置文件
- data/chat_history.json - 聊天记录
- data/plugins/installed/ - 插件代码
- data/plugins/plugins_config/ - 插件配置
- data/plugins/plugins_data/ - 插件持久化数据
- data/temp/ - 临时文件
"""

import shutil
import sys
from pathlib import Path
from typing import Optional


class DataManager:
    """数据目录管理器"""

    def __init__(self, custom_data_dir: Optional[Path] = None):
        """
        初始化数据管理器

        Args:
            custom_data_dir: 自定义数据目录路径,为None则使用默认路径
        """
        self._custom_data_dir = custom_data_dir
        self._data_dir: Optional[Path] = None

    @property
    def data_dir(self) -> Path:
        """获取数据根目录"""
        if self._data_dir is not None:
            return self._data_dir

        if self._custom_data_dir:
            self._data_dir = self._custom_data_dir
        else:
            # 默认使用项目根目录下的 data 文件夹
            if getattr(sys, "frozen", False):
                project_root = Path(sys.executable).parent
            else:
                project_root = Path(__file__).parent.parent
            self._data_dir = project_root / "data"

        self._data_dir.mkdir(parents=True, exist_ok=True)
        return self._data_dir

    @property
    def config_file(self) -> Path:
        """配置文件路径"""
        return self.data_dir / "config.json"

    @property
    def chat_history_file(self) -> Path:
        """聊天记录文件路径"""
        return self.data_dir / "chat_history.json"

    @property
    def plugins_dir(self) -> Path:
        """插件根目录"""
        return self.data_dir / "plugins"

    @property
    def plugins_installed_dir(self) -> Path:
        """插件代码目录"""
        return self.plugins_dir / "installed"

    @property
    def plugins_config_dir(self) -> Path:
        """插件配置目录"""
        return self.plugins_dir / "plugins_config"

    @property
    def plugins_data_dir(self) -> Path:
        """插件数据目录"""
        return self.plugins_dir / "plugins_data"

    @property
    def temp_dir(self) -> Path:
        """临时文件目录"""
        return self.data_dir / "temp"

    @property
    def images_dir(self) -> Path:
        """图片存储目录"""
        return self.temp_dir / "images"

    @property
    def screenshots_dir(self) -> Path:
        """截图目录"""
        return self.temp_dir / "screenshots"

    def get_plugin_config_file(self, plugin_name: str) -> Path:
        """获取指定插件的配置文件路径"""
        return self.plugins_config_dir / f"{plugin_name}.json"

    def get_plugin_data_dir(self, plugin_name: str) -> Path:
        """获取指定插件的数据目录"""
        return self.plugins_data_dir / plugin_name

    def ensure_structure(self) -> None:
        """确保数据目录结构完整"""
        dirs_to_create = [
            self.data_dir,
            self.plugins_dir,
            self.plugins_installed_dir,
            self.plugins_config_dir,
            self.plugins_data_dir,
            self.temp_dir,
            self.images_dir,
            self.screenshots_dir,
        ]

        for dir_path in dirs_to_create:
            dir_path.mkdir(parents=True, exist_ok=True)

    def migrate_from_legacy(
        self, old_config_dir: Path, old_temp_dir: Path, logger=None
    ) -> bool:
        """
        从旧版本目录结构迁移数据

        Args:
            old_config_dir: 旧配置目录(平台配置目录)
            old_temp_dir: 旧临时文件目录
            logger: 日志记录器

        Returns:
            是否执行了迁移
        """

        def log(msg: str) -> None:
            if logger:
                logger.info(f"[迁移] {msg}")
            else:
                print(f"[迁移] {msg}")

        # 如果使用了自定义数据目录,不执行迁移
        if self._custom_data_dir:
            log("使用自定义数据目录,跳过迁移")
            return False

        # 检查是否已经迁移过
        migration_flag = self.data_dir / ".migrated"
        if migration_flag.exists():
            log("数据已迁移过,跳过")
            return False

        # 确保新目录结构存在
        self.ensure_structure()

        migrated = False

        # 迁移配置文件
        old_config_file = old_config_dir / "config.json"
        if old_config_file.exists() and not self.config_file.exists():
            try:
                shutil.copy2(old_config_file, self.config_file)
                log(f"迁移配置文件: {old_config_file} -> {self.config_file}")
                migrated = True
            except Exception as e:
                log(f"配置文件迁移失败: {e}")

        # 迁移聊天记录
        old_chat_history = old_config_dir / "chat_history.json"
        if old_chat_history.exists() and not self.chat_history_file.exists():
            try:
                shutil.copy2(old_chat_history, self.chat_history_file)
                log(f"迁移聊天记录: {old_chat_history} -> {self.chat_history_file}")
                migrated = True
            except Exception as e:
                log(f"聊天记录迁移失败: {e}")

        # 迁移临时文件
        if old_temp_dir.exists():
            for item in old_temp_dir.iterdir():
                try:
                    target = self.temp_dir / item.name
                    if not target.exists():
                        if item.is_dir():
                            shutil.copytree(item, target)
                        else:
                            shutil.copy2(item, target)
                        log(f"迁移临时文件: {item} -> {target}")
                        migrated = True
                except Exception as e:
                    log(f"临时文件迁移失败 {item}: {e}")

        # 迁移旧插件目录(如果存在)
        old_plugins_base = Path(__file__).parent / "plugins"
        old_plugins_installed = old_plugins_base / "installed"
        old_plugins_configs = old_plugins_base / "configs"

        if old_plugins_installed.exists():
            for item in old_plugins_installed.iterdir():
                try:
                    target = self.plugins_installed_dir / item.name
                    if not target.exists():
                        if item.is_dir():
                            shutil.copytree(item, target)
                        else:
                            shutil.copy2(item, target)
                        log(f"迁移插件代码: {item} -> {target}")
                        migrated = True
                except Exception as e:
                    log(f"插件代码迁移失败 {item}: {e}")

        if old_plugins_configs.exists():
            for item in old_plugins_configs.iterdir():
                try:
                    target = self.plugins_config_dir / item.name
                    if not target.exists():
                        shutil.copy2(item, target)
                        log(f"迁移插件配置: {item} -> {target}")
                        migrated = True
                except Exception as e:
                    log(f"插件配置迁移失败 {item}: {e}")

        # 创建迁移标记
        if migrated:
            migration_flag.touch()
            log("迁移完成")

        return migrated


# 全局单例
_data_manager: Optional[DataManager] = None


def get_data_manager(custom_data_dir: Optional[Path] = None) -> DataManager:
    """获取数据管理器单例"""
    global _data_manager
    if _data_manager is None:
        _data_manager = DataManager(custom_data_dir)
    return _data_manager


def init_data_structure(
    custom_data_dir: Optional[Path] = None, auto_migrate: bool = True, logger=None
) -> DataManager:
    """
    初始化数据目录结构

    Args:
        custom_data_dir: 自定义数据目录
        auto_migrate: 是否自动执行旧数据迁移
        logger: 日志记录器

    Returns:
        数据管理器实例
    """
    manager = get_data_manager(custom_data_dir)
    manager.ensure_structure()

    if auto_migrate:
        # 获取旧版本路径
        from .config import _get_config_dir_internal

        old_config_dir = _get_config_dir_internal()

        # 旧临时目录
        if getattr(sys, "frozen", False):
            project_root = Path(sys.executable).parent
        else:
            project_root = Path(__file__).parent.parent
        old_temp_dir = project_root / "temp"

        manager.migrate_from_legacy(old_config_dir, old_temp_dir, logger)

    return manager
