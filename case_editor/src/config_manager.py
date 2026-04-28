"""
配置管理模块
负责加载和保存应用程序配置
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载配置文件失败: {e}")
                return self._get_default_config()
        else:
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "app_name": "DSL Case Editor",
            "version": "1.0.0",
            "default_project_dir": "./projects",
            "recent_projects": [],
            "editor": {
                "font_family": "Consolas",
                "font_size": 12,
                "tab_size": 4,
                "show_line_numbers": True,
                "word_wrap": False
            },
            "ai": {
                "enabled": False,
                "api_key": "",
                "model": "gpt-4",
                "max_tokens": 2000
            },
            "oss": {
                "enabled": False,
                "endpoint": "",
                "access_key_id": "",
                "access_key_secret": "",
                "bucket_name": ""
            }
        }
    
    def save_config(self) -> bool:
        """保存配置文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def set(self, key: str, value: Any) -> None:
        """设置配置项"""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
    
    def add_recent_project(self, project_path: str) -> None:
        """添加最近打开的项目"""
        recent_projects = self.get('recent_projects', [])
        if project_path in recent_projects:
            recent_projects.remove(project_path)
        recent_projects.insert(0, project_path)
        # 只保留最近10个项目
        self.set('recent_projects', recent_projects[:10])
        self.save_config()
    
    def get_recent_projects(self) -> list:
        """获取最近打开的项目列表"""
        return self.get('recent_projects', [])
