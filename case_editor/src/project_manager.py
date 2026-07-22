"""
项目管理模块
负责项目的创建、打开、保存和管理
"""
import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime


class ProjectManager:
    """项目管理器"""
    
    def __init__(self):
        self.current_project_path: Optional[Path] = None
        self.project_config: Dict[str, Any] = {}
    
    def create_project(self, project_path: str, project_name: str) -> bool:
        """
        创建新项目
        
        Args:
            project_path: 项目根目录路径
            project_name: 项目名称
            
        Returns:
            bool: 是否创建成功
        """
        try:
            project_dir = Path(project_path) / project_name
            
            # 创建项目目录结构
            # CANoe 目录
            canoe_subdirs = [
                'CANoe/dbc_file',
                'CANoe/env_dbc',
                'CANoe/system_variable',
                'CANoe/mapping_file',
                'CANoe/project_file'
            ]
            
            # Simulink 目录
            simulink_subdirs = [
                'Simulink/project_info'
            ]
            
            # DSL Case 目录
            dsl_subdirs = [
                'dsl_case'
            ]

            # Automation Case 目录
            automation_subdirs = [
                'automation_case/py_cases',
                'automation_case/json_cases'
            ]

            # Scene 目录
            scene_subdirs = [
                'Scene'
            ]

            # Test Results 目录
            test_results_subdirs = [
                'Test Results/trace data',
                'Test Results/record data',
                'Test Results/log data',
                'Test Results/report data'
            ]

            for subdir in canoe_subdirs + simulink_subdirs + dsl_subdirs + automation_subdirs + scene_subdirs + test_results_subdirs:
                (project_dir / subdir).mkdir(parents=True, exist_ok=True)
            
            # 创建项目配置文件
            project_config = {
                "project_name": project_name,
                "created_time": datetime.now().isoformat(),
                "modified_time": datetime.now().isoformat(),
                "version": "1.0.0",
                "canoe": {
                    "dbc_files": {},
                    "env_dbc_files": [],
                    "system_variable_files": [],
                    "can_channel_mapping": {},
                    "project_path": ""
                },
                "simulink": {
                    "files": []
                },
                "dsl_cases": [],
                "automation_cases": {
                    "py_cases": [],
                    "json_cases": []
                },
                "scene_mappings": [],
                "test_requirements": [],
                "test_results": {
                    "trace_data": [],
                    "record_data": [],
                    "log_data": [],
                    "report_data": []
                },
                "automation": {
                    "set_preset": {
                        "preset_signals": [],
                        "preset_scene": {}
                    },
                    "set_template": {}
                }
            }
            
            config_path = project_dir / "project.json"
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(project_config, f, indent=2, ensure_ascii=False)
            
            self.current_project_path = project_dir
            self.project_config = project_config
            
            return True
        except Exception as e:
            print(f"创建项目失败: {e}")
            return False
    
    def open_project(self, project_path: str) -> bool:
        """
        打开现有项目
        
        Args:
            project_path: 项目路径
            
        Returns:
            bool: 是否打开成功
        """
        try:
            project_dir = Path(project_path)
            config_path = project_dir / "project.json"
            
            if not config_path.exists():
                print("项目配置文件不存在")
                return False
            
            with open(config_path, 'r', encoding='utf-8') as f:
                self.project_config = json.load(f)
            
            self.current_project_path = project_dir
            
            # 确保Scene目录存在（兼容旧项目）
            scene_dir = self.current_project_path / "Scene"
            scene_dir.mkdir(parents=True, exist_ok=True)
            
            # 如果配置中没有scene_mappings字段，添加它
            if "scene_mappings" not in self.project_config:
                self.project_config["scene_mappings"] = []
                self.save_project()

            # 如果配置中没有automation_cases字段，添加它
            if "automation_cases" not in self.project_config:
                self.project_config["automation_cases"] = {
                    "py_cases": [],
                    "json_cases": []
                }
                self.save_project()

            # 同步 automation_cases 目录结构到配置
            self.sync_automation_cases()

            # 确保 Test Results 目录存在（兼容旧项目）
            test_results_dir = self.current_project_path / "Test Results"
            trace_data_dir = test_results_dir / "trace data"
            record_data_dir = test_results_dir / "record data"
            log_data_dir = test_results_dir / "log data"
            report_data_dir = test_results_dir / "report data"
            trace_data_dir.mkdir(parents=True, exist_ok=True)
            record_data_dir.mkdir(parents=True, exist_ok=True)
            log_data_dir.mkdir(parents=True, exist_ok=True)
            report_data_dir.mkdir(parents=True, exist_ok=True)

            # 如果配置中没有test_results字段，添加它
            if "test_results" not in self.project_config:
                self.project_config["test_results"] = {
                    "trace_data": [],
                    "record_data": [],
                    "log_data": [],
                    "report_data": []
                }
                self.save_project()

            # 兼容旧项目：确保 test_results 包含新字段
            if "log_data" not in self.project_config.get("test_results", {}):
                self.project_config["test_results"]["log_data"] = []
                self.project_config["test_results"]["report_data"] = []
                self.save_project()

            # 如果配置中没有automation字段，添加它
            if "automation" not in self.project_config:
                self.project_config["automation"] = {
                    "set_preset": {
                        "preset_signals": [],
                        "preset_scene": {}
                    },
                    "set_template": {}
                }
                self.save_project()

            # 同步 test_results 目录结构到配置
            self.sync_test_results()

            return True
        except Exception as e:
            print(f"打开项目失败: {e}")
            return False
    
    def save_project(self) -> bool:
        """
        保存项目配置
        
        Returns:
            bool: 是否保存成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            self.project_config["modified_time"] = datetime.now().isoformat()
            config_path = self.current_project_path / "project.json"
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.project_config, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"保存项目失败: {e}")
            return False
    
    def close_project(self) -> None:
        """关闭当前项目"""
        self.current_project_path = None
        self.project_config = {}
    
    def is_project_open(self) -> bool:
        """检查是否有项目打开"""
        return self.current_project_path is not None
    
    def get_project_path(self) -> Optional[Path]:
        """获取当前项目路径"""
        return self.current_project_path
    
    def get_project_name(self) -> Optional[str]:
        """获取当前项目名称"""
        return self.project_config.get("project_name")
    
    def add_dbc_file(self, dbc_path: str, copy_to_project: bool = True) -> bool:
        """
        添加DBC文件到项目

        Args:
            dbc_path: DBC文件路径
            copy_to_project: 是否复制到项目目录

        Returns:
            bool: 是否添加成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False

        try:
            dbc_file = Path(dbc_path)
            if not dbc_file.exists():
                print(f"DBC文件不存在: {dbc_path}")
                return False

            if copy_to_project:
                # 复制到项目的CANoe/dbc_file目录
                target_dir = self.current_project_path / "CANoe" / "dbc_file"
                target_path = target_dir / dbc_file.name
                shutil.copy2(dbc_file, target_path)
                relative_path = f"CANoe/dbc_file/{dbc_file.name}"
            else:
                relative_path = str(dbc_file)

            # 更新项目配置
            if "canoe" not in self.project_config:
                self.project_config["canoe"] = {}

            dbc_files = self.project_config["canoe"].get("dbc_files", {})

            # 兼容旧格式（列表）
            if isinstance(dbc_files, list):
                # 转换为新格式（字典）
                new_dbc_files = {}
                for old_path in dbc_files:
                    new_dbc_files[old_path] = {
                        "path": old_path,
                        "short_name": "",
                        "channel": 0
                    }
                dbc_files = new_dbc_files

            if relative_path not in dbc_files:
                dbc_files[relative_path] = {
                    "path": relative_path,
                    "short_name": "",
                    "channel": 0
                }

            self.project_config["canoe"]["dbc_files"] = dbc_files

            return self.save_project()
        except Exception as e:
            print(f"添加DBC文件失败: {e}")
            return False
    
    def add_env_dbc_file(self, dbc_path: str, copy_to_project: bool = True) -> bool:
        """
        添加环境变量DBC文件到项目
        
        Args:
            dbc_path: 环境变量DBC文件路径
            copy_to_project: 是否复制到项目目录
            
        Returns:
            bool: 是否添加成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            dbc_file = Path(dbc_path)
            if not dbc_file.exists():
                print(f"环境变量DBC文件不存在: {dbc_path}")
                return False
            
            if copy_to_project:
                # 复制到项目的CANoe/env_dbc目录
                target_dir = self.current_project_path / "CANoe" / "env_dbc"
                target_path = target_dir / dbc_file.name
                shutil.copy2(dbc_file, target_path)
                relative_path = f"CANoe/env_dbc/{dbc_file.name}"
            else:
                relative_path = str(dbc_file)
            
            # 更新项目配置
            if "canoe" not in self.project_config:
                self.project_config["canoe"] = {}
            if "env_dbc_files" not in self.project_config["canoe"]:
                self.project_config["canoe"]["env_dbc_files"] = []
            
            if relative_path not in self.project_config["canoe"]["env_dbc_files"]:
                self.project_config["canoe"]["env_dbc_files"].append(relative_path)
            
            return self.save_project()
        except Exception as e:
            print(f"添加环境变量DBC文件失败: {e}")
            return False
    
    def add_system_variable_file(self, file_path: str, copy_to_project: bool = True) -> bool:
        """
        添加系统变量文件到项目
        
        Args:
            file_path: 系统变量文件路径
            copy_to_project: 是否复制到项目目录
            
        Returns:
            bool: 是否添加成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            var_file = Path(file_path)
            if not var_file.exists():
                print(f"系统变量文件不存在: {file_path}")
                return False
            
            if copy_to_project:
                # 复制到项目的CANoe/system_variable目录
                target_dir = self.current_project_path / "CANoe" / "system_variable"
                target_path = target_dir / var_file.name
                shutil.copy2(var_file, target_path)
                relative_path = f"CANoe/system_variable/{var_file.name}"
            else:
                relative_path = str(var_file)
            
            # 更新项目配置
            if "canoe" not in self.project_config:
                self.project_config["canoe"] = {}
            if "system_variable_files" not in self.project_config["canoe"]:
                self.project_config["canoe"]["system_variable_files"] = []
            
            if relative_path not in self.project_config["canoe"]["system_variable_files"]:
                self.project_config["canoe"]["system_variable_files"].append(relative_path)
            
            return self.save_project()
        except Exception as e:
            print(f"添加系统变量文件失败: {e}")
    
    def remove_dbc_file(self, file_name: str) -> tuple:
        """
        删除DBC文件

        Args:
            file_name: DBC文件名

        Returns:
            tuple: (bool是否成功, str被删除文件的完整路径或None)
        """
        if not self.current_project_path:
            return (False, None)

        try:
            # 删除文件
            file_dir = self.current_project_path / "CANoe" / "dbc_file"
            file_path = file_dir / file_name
            abs_path = str(file_path) if file_path.exists() else None

            if file_path.exists():
                file_path.unlink()

            # 从配置中移除
            if "canoe" in self.project_config and "dbc_files" in self.project_config["canoe"]:
                dbc_files = self.project_config["canoe"]["dbc_files"]
                # 兼容旧格式（列表）和新格式（字典）
                if isinstance(dbc_files, list):
                    self.project_config["canoe"]["dbc_files"] = [
                        f for f in dbc_files if not f.endswith(file_name)
                    ]
                else:
                    # 字典格式，检查 path 字段
                    keys_to_remove = []
                    for key, value in dbc_files.items():
                        if isinstance(value, dict) and value.get("path", "").endswith(file_name):
                            keys_to_remove.append(key)
                    for key in keys_to_remove:
                        del dbc_files[key]

                # 同时从 can_channel_mapping 中移除
                if "can_channel_mapping" in self.project_config["canoe"]:
                    mapping = self.project_config["canoe"]["can_channel_mapping"]
                    keys_to_remove = [k for k in mapping.keys() if k.endswith(file_name)]
                    for key in keys_to_remove:
                        del mapping[key]

            self.save_project()
            return (True, abs_path)
        except Exception as e:
            print(f"删除DBC文件失败: {e}")
            return (False, None)
    
    def remove_env_dbc_file(self, file_name: str) -> tuple:
        """
        删除环境变量DBC文件

        Args:
            file_name: 环境变量DBC文件名

        Returns:
            tuple: (bool是否成功, str被删除文件的完整路径或None)
        """
        if not self.current_project_path:
            return (False, None)

        try:
            # 删除文件
            file_dir = self.current_project_path / "CANoe" / "env_dbc"
            file_path = file_dir / file_name
            abs_path = str(file_path) if file_path.exists() else None

            if file_path.exists():
                file_path.unlink()

            # 从配置中移除
            if "canoe" in self.project_config and "env_dbc_files" in self.project_config["canoe"]:
                self.project_config["canoe"]["env_dbc_files"] = [
                    f for f in self.project_config["canoe"]["env_dbc_files"]
                    if not f.endswith(file_name)
                ]

            self.save_project()
            return (True, abs_path)
        except Exception as e:
            print(f"删除环境变量DBC文件失败: {e}")
            return (False, None)
    
    def remove_system_variable_file(self, file_name: str) -> tuple:
        """
        删除系统变量文件

        Args:
            file_name: 系统变量文件名

        Returns:
            tuple: (bool是否成功, str被删除文件的完整路径或None)
        """
        if not self.current_project_path:
            return (False, None)

        try:
            # 删除文件
            file_dir = self.current_project_path / "CANoe" / "system_variable"
            file_path = file_dir / file_name
            abs_path = str(file_path) if file_path.exists() else None

            if file_path.exists():
                file_path.unlink()

            # 从配置中移除
            if "canoe" in self.project_config and "system_variable_files" in self.project_config["canoe"]:
                self.project_config["canoe"]["system_variable_files"] = [
                    f for f in self.project_config["canoe"]["system_variable_files"]
                    if not f.endswith(file_name)
                ]

            self.save_project()
            return (True, abs_path)
        except Exception as e:
            print(f"删除系统变量文件失败: {e}")
            return (False, None)
    
    def set_can_channel_mapping(self, mapping: Dict[str, Dict]) -> bool:
        """
        设置CAN通道映射关系

        Args:
            mapping: DBC文件路径到映射信息的字典
                    格式: {dbc_path: {"channel": int, "short_name": str}}

        Returns:
            bool: 是否设置成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False

        try:
            # 保存到项目配置
            if "canoe" not in self.project_config:
                self.project_config["canoe"] = {}

            # 转换为相对路径存储
            relative_mapping = {}
            dbc_files_dict = {}
            for dbc_path, info in mapping.items():
                # 转换为相对路径
                abs_path = Path(dbc_path)
                if abs_path.is_absolute():
                    try:
                        rel_path = str(abs_path.relative_to(self.current_project_path))
                    except ValueError:
                        rel_path = str(abs_path)
                else:
                    rel_path = str(abs_path)

                relative_mapping[rel_path] = info

                # 更新 dbc_files 字典结构，键为 "CAN {channel+1}"
                channel = info.get("channel", 0)
                short_name = info.get("short_name", "")
                can_key = f"CAN {channel + 1}"
                dbc_files_dict[can_key] = {
                    "path": rel_path,
                    "short_name": short_name,
                    "channel": channel
                }

            self.project_config["canoe"]["can_channel_mapping"] = relative_mapping
            self.project_config["canoe"]["dbc_files"] = dbc_files_dict

            # 保存到CANoe/mapping_file目录
            mapping_dir = self.current_project_path / "CANoe" / "mapping_file"
            mapping_file = mapping_dir / "can_channel_mapping.json"

            # 创建以 CAN Channel 为 key 的格式化映射文件
            formatted_mapping = {}
            for dbc_path, info in mapping.items():
                dbc_name = Path(dbc_path).name
                channel = info.get("channel", 0)
                short_name = info.get("short_name", "")
                formatted_mapping[str(channel)] = {
                    "path": dbc_name,
                    "short_name": short_name,
                    "channel": channel
                }

            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(formatted_mapping, f, indent=4, ensure_ascii=False)

            return self.save_project()
        except Exception as e:
            print(f"设置CAN通道映射失败: {e}")
            return False

    def get_can_channel_mapping(self) -> Dict[str, Dict]:
        """
        获取CAN通道映射关系（返回相对路径的映射）

        Returns:
            Dict[str, Dict]: 格式 {dbc_rel_path: {"channel": int, "short_name": str}}
        """
        return self.project_config.get("canoe", {}).get("can_channel_mapping", {})
    
    def get_dbc_files(self) -> List[str]:
        """获取项目中的DBC文件列表（返回相对路径）"""
        dbc_files = self.project_config.get("canoe", {}).get("dbc_files", {})
        # 兼容旧格式（列表）和新格式（字典）
        if isinstance(dbc_files, list):
            return dbc_files
        else:
            # 新格式字典，从值中提取path
            return [v.get("path", "") for v in dbc_files.values() if isinstance(v, dict) and v.get("path")]

    def get_env_dbc_files(self) -> List[str]:
        """获取项目中的环境变量DBC文件列表（返回绝对路径）"""
        relative_paths = self.project_config.get("canoe", {}).get("env_dbc_files", [])
        if not self.current_project_path:
            return relative_paths
        # 转换为绝对路径
        absolute_paths = []
        for rel_path in relative_paths:
            abs_path = self.current_project_path / rel_path
            absolute_paths.append(str(abs_path))
        return absolute_paths
    
    def get_system_variable_files(self) -> List[str]:
        """获取项目中的系统变量文件列表"""
        return self.project_config.get("canoe", {}).get("system_variable_files", [])
    
    def set_canoe_project_path(self, project_path: str) -> bool:
        """
        设置CANoe工程文件地址
        
        Args:
            project_path: CANoe工程文件路径
            
        Returns:
            bool: 是否设置成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            if "canoe" not in self.project_config:
                self.project_config["canoe"] = {}
            self.project_config["canoe"]["project_path"] = project_path
            return self.save_project()
        except Exception as e:
            print(f"设置CANoe工程文件地址失败: {e}")
            return False
    
    def get_canoe_project_path(self) -> str:
        """获取CANoe工程文件地址"""
        return self.project_config.get("canoe", {}).get("project_path", "")
    
    def add_simulink_file(self, file_path: str, file_type: str, copy_to_project: bool = True) -> bool:
        """
        添加Simulink文件到项目
        
        Args:
            file_path: 文件路径
            file_type: 文件类型 ("m_script", "mat_file", "simulink_model")
            copy_to_project: 是否复制到项目目录
            
        Returns:
            bool: 是否添加成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            file = Path(file_path)
            if not file.exists():
                print(f"文件不存在: {file_path}")
                return False
            
            if copy_to_project:
                # 复制到项目的Simulink/project_info目录
                target_dir = self.current_project_path / "Simulink" / "project_info"
                target_path = target_dir / file.name
                shutil.copy2(file, target_path)
                relative_path = f"Simulink/project_info/{file.name}"
            else:
                relative_path = str(file)
            
            # 更新项目配置
            if "simulink" not in self.project_config:
                self.project_config["simulink"] = {}
            if "files" not in self.project_config["simulink"]:
                self.project_config["simulink"]["files"] = []
            
            file_info = {
                "name": file.name,
                "path": relative_path,
                "type": file_type,
                "created_time": datetime.now().isoformat()
            }
            
            # 检查是否已存在
            existing_files = [f for f in self.project_config["simulink"]["files"] if f["name"] == file.name]
            if existing_files:
                # 更新现有文件
                idx = self.project_config["simulink"]["files"].index(existing_files[0])
                self.project_config["simulink"]["files"][idx] = file_info
            else:
                # 添加新文件
                self.project_config["simulink"]["files"].append(file_info)
            
            return self.save_project()
        except Exception as e:
            print(f"添加Simulink文件失败: {e}")
            return False
    
    def get_simulink_files(self) -> List[Dict[str, Any]]:
        """获取项目中的Simulink文件列表"""
        return self.project_config.get("simulink", {}).get("files", [])
    
    def get_full_path(self, relative_path: str) -> Optional[Path]:
        """
        获取相对路径的完整路径
        
        Args:
            relative_path: 相对路径
            
        Returns:
            完整路径，如果项目未打开则返回None
        """
        if not self.current_project_path:
            return None
        
        # 如果是绝对路径，直接返回
        if Path(relative_path).is_absolute():
            return Path(relative_path)
        
        # 否则相对于项目目录
        return self.current_project_path / relative_path
    
    def add_dsl_case(self, case_name: str, case_content: str, directory: str = "") -> bool:
        """
        添加DSL case到项目
        
        Args:
            case_name: case名称
            case_content: case内容
            directory: 目录路径（相对于dsl_case目录），例如 "subdir1/subdir2"
            
        Returns:
            bool: 是否添加成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            # 保存到dsl_case目录（支持子目录）
            case_dir = self.current_project_path / "dsl_case"
            if directory:
                case_dir = case_dir / directory
            
            # 确保目录存在
            case_dir.mkdir(parents=True, exist_ok=True)
            
            case_file = case_dir / f"{case_name}.dsl"
            
            with open(case_file, 'w', encoding='utf-8') as f:
                f.write(case_content)
            
            # 更新项目配置
            if "dsl_cases" not in self.project_config:
                self.project_config["dsl_cases"] = []
            
            # 构建相对路径
            relative_path = f"dsl_case/{directory}/{case_name}.dsl" if directory else f"dsl_case/{case_name}.dsl"
            
            case_info = {
                "name": case_name,
                "file": relative_path,
                "directory": directory,
                "created_time": datetime.now().isoformat()
            }
            
            # 检查是否已存在
            existing_cases = [c for c in self.project_config["dsl_cases"] if c["name"] == case_name and c.get("directory", "") == directory]
            if existing_cases:
                # 更新现有case
                idx = self.project_config["dsl_cases"].index(existing_cases[0])
                self.project_config["dsl_cases"][idx] = case_info
            else:
                # 添加新case
                self.project_config["dsl_cases"].append(case_info)
            
            return self.save_project()
        except Exception as e:
            print(f"添加DSL case失败: {e}")
            return False
    
    def get_dsl_cases(self) -> List[Dict[str, Any]]:
        """获取项目中的DSL case列表"""
        return self.project_config.get("dsl_cases", [])
    
    def load_dsl_case(self, case_name: str, directory: str = "") -> Optional[str]:
        """
        加载DSL case内容
        
        Args:
            case_name: case名称
            directory: 目录路径（相对于dsl_case目录）
            
        Returns:
            case内容，如果加载失败则返回None
        """
        if not self.current_project_path:
            return None
        
        try:
            case_dir = self.current_project_path / "dsl_case"
            if directory:
                case_dir = case_dir / directory
            
            case_file = case_dir / f"{case_name}.dsl"
            
            if not case_file.exists():
                return None
            
            with open(case_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"加载DSL case失败: {e}")
            return None
    
    def delete_dsl_case(self, case_name: str, directory: str = "") -> bool:
        """
        删除DSL case
        
        Args:
            case_name: case名称
            directory: 目录路径（相对于dsl_case目录）
            
        Returns:
            bool: 是否删除成功
        """
        if not self.current_project_path:
            return False
        
        try:
            # 删除文件
            case_dir = self.current_project_path / "dsl_case"
            if directory:
                case_dir = case_dir / directory
            
            case_file = case_dir / f"{case_name}.dsl"
            
            if case_file.exists():
                case_file.unlink()
            
            # 从配置中移除
            if "dsl_cases" in self.project_config:
                self.project_config["dsl_cases"] = [
                    c for c in self.project_config["dsl_cases"]
                    if not (c["name"] == case_name and c.get("directory", "") == directory)
                ]
            
            return self.save_project()
        except Exception as e:
            print(f"删除DSL case失败: {e}")
            return False
    
    def create_dsl_directory(self, directory_name: str, parent_directory: str = "") -> bool:
        """
        创建DSL case目录
        
        Args:
            directory_name: 目录名称
            parent_directory: 父目录路径（相对于dsl_case目录）
            
        Returns:
            bool: 是否创建成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            # 创建目录
            case_dir = self.current_project_path / "dsl_case"
            if parent_directory:
                case_dir = case_dir / parent_directory
            
            new_dir = case_dir / directory_name
            new_dir.mkdir(parents=True, exist_ok=True)
            
            return True
        except Exception as e:
            print(f"创建DSL目录失败: {e}")
            return False
    
    def delete_dsl_directory(self, directory: str) -> bool:
        """
        删除DSL case目录及其内容
        
        Args:
            directory: 目录路径（相对于dsl_case目录）
            
        Returns:
            bool: 是否删除成功
        """
        if not self.current_project_path:
            return False
        
        try:
            # 删除目录
            case_dir = self.current_project_path / "dsl_case"
            target_dir = case_dir / directory
            
            if target_dir.exists() and target_dir.is_dir():
                shutil.rmtree(target_dir)
            
            # 从配置中移除该目录下的所有case
            if "dsl_cases" in self.project_config:
                self.project_config["dsl_cases"] = [
                    c for c in self.project_config["dsl_cases"]
                    if not c.get("directory", "").startswith(directory)
                ]
            
            return self.save_project()
        except Exception as e:
            print(f"删除DSL目录失败: {e}")
            return False
    
    def rename_dsl_case(self, old_case_name: str, new_case_name: str, directory: str = "") -> bool:
        """
        重命名DSL case文件
        
        Args:
            old_case_name: 旧的case名称
            new_case_name: 新的case名称
            directory: 目录路径（相对于dsl_case目录）
            
        Returns:
            bool: 是否重命名成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            # 重命名文件
            case_dir = self.current_project_path / "dsl_case"
            if directory:
                case_dir = case_dir / directory
            
            old_file = case_dir / f"{old_case_name}.dsl"
            new_file = case_dir / f"{new_case_name}.dsl"
            
            if not old_file.exists():
                print(f"文件不存在: {old_file}")
                return False
            
            # 检查新文件名是否已存在
            if new_file.exists():
                print(f"文件已存在: {new_file}")
                return False
            
            # 重命名文件
            old_file.rename(new_file)
            
            # 更新项目配置
            if "dsl_cases" in self.project_config:
                for case_info in self.project_config["dsl_cases"]:
                    if case_info["name"] == old_case_name and case_info.get("directory", "") == directory:
                        case_info["name"] = new_case_name
                        case_info["file"] = f"dsl_case/{directory}/{new_case_name}.dsl" if directory else f"dsl_case/{new_case_name}.dsl"
                        break
            
            return self.save_project()
        except Exception as e:
            print(f"重命名DSL case失败: {e}")
            return False
    
    def rename_dsl_directory(self, old_directory: str, new_directory_name: str) -> bool:
        """
        重命名DSL case目录
        
        Args:
            old_directory: 旧的目录路径（相对于dsl_case目录）
            new_directory_name: 新的目录名称（仅最后一部分）
            
        Returns:
            bool: 是否重命名成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            # 构建完整路径
            case_dir = self.current_project_path / "dsl_case"
            old_dir_path = case_dir / old_directory
            
            if not old_dir_path.exists() or not old_dir_path.is_dir():
                print(f"目录不存在: {old_directory}")
                return False
            
            # 获取父目录和新目录名
            parent_path = old_dir_path.parent
            new_dir_path = parent_path / new_directory_name
            
            # 检查新目录名是否已存在
            if new_dir_path.exists():
                print(f"目录已存在: {new_directory_name}")
                return False
            
            # 重命名目录
            old_dir_path.rename(new_dir_path)
            
            # 构建新的相对路径
            if "/" in old_directory:
                parts = old_directory.split("/")
                parts[-1] = new_directory_name
                new_directory = "/".join(parts)
            else:
                new_directory = new_directory_name
            
            # 更新项目配置中所有引用该目录的case
            if "dsl_cases" in self.project_config:
                for case_info in self.project_config["dsl_cases"]:
                    old_dir = case_info.get("directory", "")
                    if old_dir == old_directory or old_dir.startswith(old_directory + "/"):
                        # 更新目录路径
                        if old_dir == old_directory:
                            case_info["directory"] = new_directory
                        else:
                            # 处理子目录
                            suffix = old_dir[len(old_directory):]
                            case_info["directory"] = new_directory + suffix
                        
                        # 更新文件路径
                        case_name = case_info["name"]
                        case_info["file"] = f"dsl_case/{case_info['directory']}/{case_name}.dsl"
            
            return self.save_project()
        except Exception as e:
            print(f"重命名DSL目录失败: {e}")
            return False
    
    def copy_dsl_case(self, case_name: str, new_case_name: str, directory: str = "") -> bool:
        """
        复制DSL case文件
        
        Args:
            case_name: 原case名称
            new_case_name: 新case名称
            directory: 目录路径（相对于dsl_case目录）
            
        Returns:
            bool: 是否复制成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            # 复制文件
            case_dir = self.current_project_path / "dsl_case"
            if directory:
                case_dir = case_dir / directory
            
            old_file = case_dir / f"{case_name}.dsl"
            new_file = case_dir / f"{new_case_name}.dsl"
            
            if not old_file.exists():
                print(f"文件不存在: {old_file}")
                return False
            
            # 检查新文件名是否已存在，如果存在则自动添加 _copy 后缀（VSCode风格）
            final_name = new_case_name
            while new_file.exists():
                final_name = f"{final_name}_copy"
                new_file = case_dir / f"{final_name}.dsl"
            
            # 复制文件
            shutil.copy2(old_file, new_file)
            
            # 更新项目配置
            if "dsl_cases" not in self.project_config:
                self.project_config["dsl_cases"] = []
            
            # 构建相对路径
            relative_path = f"dsl_case/{directory}/{final_name}.dsl" if directory else f"dsl_case/{final_name}.dsl"
            
            case_info = {
                "name": final_name,
                "file": relative_path,
                "directory": directory,
                "created_time": datetime.now().isoformat()
            }
            
            self.project_config["dsl_cases"].append(case_info)
            
            return self.save_project()
        except Exception as e:
            print(f"复制DSL case失败: {e}")
            return False
    
    def copy_dsl_directory(self, directory: str, new_directory_name: str) -> bool:
        """
        复制DSL case目录及其内容
        
        Args:
            directory: 原目录路径（相对于dsl_case目录）
            new_directory_name: 新目录名称（仅最后一部分）
            
        Returns:
            bool: 是否复制成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            # 构建完整路径
            case_dir = self.current_project_path / "dsl_case"
            old_dir_path = case_dir / directory
            
            if not old_dir_path.exists() or not old_dir_path.is_dir():
                print(f"目录不存在: {directory}")
                return False
            
            # 获取父目录和新目录名
            parent_path = old_dir_path.parent
            new_dir_path = parent_path / new_directory_name
            
            # 检查新目录名是否已存在，如果存在则自动添加 _copy 后缀（VSCode风格）
            final_name = new_directory_name
            while new_dir_path.exists():
                final_name = f"{final_name}_copy"
                new_dir_path = parent_path / final_name
            
            # 复制目录
            shutil.copytree(old_dir_path, new_dir_path)
            
            # 构建新的相对路径
            if "/" in directory:
                parts = directory.split("/")
                parts[-1] = final_name
                new_directory = "/".join(parts)
            else:
                new_directory = final_name
            
            # 更新项目配置，添加新目录下的所有case
            if "dsl_cases" not in self.project_config:
                self.project_config["dsl_cases"] = []
            
            # 遍历新目录，添加所有.dsl文件到配置
            for dsl_file in new_dir_path.rglob("*.dsl"):
                # 计算相对路径
                rel_path = dsl_file.relative_to(self.current_project_path / "dsl_case")
                rel_dir = str(rel_path.parent) if rel_path.parent != Path(".") else ""
                case_name = dsl_file.stem
                
                case_info = {
                    "name": case_name,
                    "file": f"dsl_case/{rel_dir}/{case_name}.dsl" if rel_dir else f"dsl_case/{case_name}.dsl",
                    "directory": rel_dir,
                    "created_time": datetime.now().isoformat()
                }
                
                self.project_config["dsl_cases"].append(case_info)
            
            return self.save_project()
        except Exception as e:
            print(f"复制DSL目录失败: {e}")
            return False
    
    def get_dsl_directory_structure(self) -> Dict[str, Any]:
        """
        获取DSL case目录结构
        
        Returns:
            目录结构字典，格式：
            {
                "name": "目录名",
                "type": "directory",
                "path": "相对路径",
                "children": [...]
            }
        """
        if not self.current_project_path:
            return {}
        
        def build_tree(path: Path, relative_path: str = "") -> Dict[str, Any]:
            """递归构建目录树"""
            node = {
                "name": path.name,
                "type": "directory" if path.is_dir() else "file",
                "path": relative_path,
                "children": []
            }
            
            if path.is_dir():
                # 排序：目录在前，文件在后
                items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
                for item in items:
                    item_relative = f"{relative_path}/{item.name}" if relative_path else item.name
                    node["children"].append(build_tree(item, item_relative))
            
            return node
        
        case_dir = self.current_project_path / "dsl_case"
        if not case_dir.exists():
            # 如果目录不存在，返回一个空的虚拟根节点
            return {
                "name": "",
                "type": "directory",
                "path": "",
                "children": []
            }
        
        # 直接返回dsl_case目录下的内容，不包含dsl_case本身
        result = {
            "name": "",
            "type": "directory",
            "path": "",
            "children": []
        }
        
        # 排序：目录在前，文件在后
        items = sorted(case_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        for item in items:
            result["children"].append(build_tree(item, item.name))
        
        return result

    def get_automation_directory_structure(self, case_type: str) -> Dict[str, Any]:
        """
        获取Automation Cases目录结构

        Args:
            case_type: "py_cases" 或 "json_cases"

        Returns:
            目录结构字典
        """
        if not self.current_project_path:
            return {}

        def build_tree(path: Path, relative_path: str = "") -> Dict[str, Any]:
            """递归构建目录树"""
            node = {
                "name": path.name,
                "type": "directory" if path.is_dir() else "file",
                "path": relative_path,
                "children": []
            }

            if path.is_dir():
                items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
                for item in items:
                    item_relative = f"{relative_path}/{item.name}" if relative_path else item.name
                    node["children"].append(build_tree(item, item_relative))

            return node

        case_dir = self.current_project_path / "automation_case" / case_type
        if not case_dir.exists():
            return {
                "name": "",
                "type": "directory",
                "path": "",
                "children": []
            }

        result = {
            "name": "",
            "type": "directory",
            "path": "",
            "children": []
        }

        items = sorted(case_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        for item in items:
            result["children"].append(build_tree(item, item.name))

        return result

    def sync_dsl_cases(self) -> bool:
        """
        同步 dsl_cases 目录结构到 project.json
        扫描 dsl_case 目录，更新配置中的列表

        Returns:
            bool: 是否同步成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False

        try:
            dsl_dir = self.current_project_path / "dsl_case"
            cases_list = []

            if dsl_dir.exists():
                # 遍历目录，收集所有 .dsl 文件
                for file_path in dsl_dir.rglob("*.dsl"):
                    relative_path = file_path.relative_to(dsl_dir)
                    directory = str(relative_path.parent) if relative_path.parent != Path(".") else ""

                    case_info = {
                        "name": file_path.stem,
                        "file": f"dsl_case/{relative_path.as_posix()}",
                        "directory": directory,
                        "modified_time": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                    }
                    cases_list.append(case_info)

            self.project_config["dsl_cases"] = cases_list
            return self.save_project()
        except Exception as e:
            print(f"同步 dsl_cases 失败: {e}")
            return False

    def sync_automation_cases(self) -> bool:
        """
        同步 automation_cases 目录结构到 project.json
        扫描 py_cases 和 json_cases 目录，更新配置中的列表

        Returns:
            bool: 是否同步成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False

        try:
            # 确保 automation_cases 配置存在
            if "automation_cases" not in self.project_config:
                self.project_config["automation_cases"] = {
                    "py_cases": [],
                    "json_cases": []
                }

            for case_type in ["py_cases", "json_cases"]:
                case_dir = self.current_project_path / "automation_case" / case_type
                cases_list = []

                if case_dir.exists():
                    # 根据类型确定文件扩展名
                    ext = ".py" if case_type == "py_cases" else ".json"

                    # 遍历目录，收集所有文件
                    for file_path in case_dir.rglob(f"*{ext}"):
                        relative_path = file_path.relative_to(case_dir)
                        directory = str(relative_path.parent) if relative_path.parent != Path(".") else ""

                        case_info = {
                            "name": file_path.stem,
                            "file": f"automation_case/{case_type}/{relative_path.as_posix()}",
                            "directory": directory,
                            "modified_time": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                        }
                        cases_list.append(case_info)

                self.project_config["automation_cases"][case_type] = cases_list

            return self.save_project()
        except Exception as e:
            print(f"同步 automation_cases 失败: {e}")
            return False

    def add_automation_case(self, case_name: str, case_type: str, directory: str = "") -> bool:
        """
        添加 automation case 到配置

        Args:
            case_name: case名称
            case_type: "py" 或 "json"
            directory: 目录路径（相对于 py_cases 或 json_cases 目录）

        Returns:
            bool: 是否添加成功
        """
        if not self.current_project_path:
            return False

        try:
            config_key = f"{case_type}_cases"
            if "automation_cases" not in self.project_config:
                self.project_config["automation_cases"] = {"py_cases": [], "json_cases": []}

            ext = ".py" if case_type == "py" else ".json"
            relative_path = f"automation_case/{config_key}/{directory}/{case_name}{ext}" if directory else f"automation_case/{config_key}/{case_name}{ext}"
            relative_path = relative_path.replace("//", "/")

            case_info = {
                "name": case_name,
                "file": relative_path,
                "directory": directory,
                "created_time": datetime.now().isoformat()
            }

            # 检查是否已存在
            existing_cases = [c for c in self.project_config["automation_cases"][config_key]
                            if c["name"] == case_name and c.get("directory", "") == directory]
            if existing_cases:
                idx = self.project_config["automation_cases"][config_key].index(existing_cases[0])
                self.project_config["automation_cases"][config_key][idx] = case_info
            else:
                self.project_config["automation_cases"][config_key].append(case_info)

            return self.save_project()
        except Exception as e:
            print(f"添加 automation case 失败: {e}")
            return False

    def remove_automation_case(self, case_name: str, case_type: str, directory: str = "") -> bool:
        """
        从配置中移除 automation case

        Args:
            case_name: case名称
            case_type: "py" 或 "json"
            directory: 目录路径

        Returns:
            bool: 是否移除成功
        """
        if not self.current_project_path:
            return False

        try:
            config_key = f"{case_type}_cases"
            if "automation_cases" in self.project_config and config_key in self.project_config["automation_cases"]:
                self.project_config["automation_cases"][config_key] = [
                    c for c in self.project_config["automation_cases"][config_key]
                    if not (c["name"] == case_name and c.get("directory", "") == directory)
                ]
                return self.save_project()
            return True
        except Exception as e:
            print(f"移除 automation case 失败: {e}")
            return False

    def rename_automation_case_in_config(self, old_name: str, new_name: str, case_type: str, directory: str = "") -> bool:
        """
        在配置中重命名 automation case

        Args:
            old_name: 旧名称
            new_name: 新名称
            case_type: "py" 或 "json"
            directory: 目录路径

        Returns:
            bool: 是否重命名成功
        """
        if not self.current_project_path:
            return False

        try:
            config_key = f"{case_type}_cases"
            if "automation_cases" in self.project_config and config_key in self.project_config["automation_cases"]:
                for case_info in self.project_config["automation_cases"][config_key]:
                    if case_info["name"] == old_name and case_info.get("directory", "") == directory:
                        case_info["name"] = new_name
                        ext = ".py" if case_type == "py" else ".json"
                        case_info["file"] = f"automation_case/{config_key}/{directory}/{new_name}{ext}" if directory else f"automation_case/{config_key}/{new_name}{ext}"
                        case_info["file"] = case_info["file"].replace("//", "/")
                return self.save_project()
            return True
        except Exception as e:
            print(f"重命名 automation case 失败: {e}")
            return False

    def get_automation_cases(self, case_type: str) -> List[Dict[str, Any]]:
        """
        获取指定类型的 automation cases 列表

        Args:
            case_type: "py" 或 "json"

        Returns:
            automation cases 列表
        """
        config_key = f"{case_type}_cases"
        if "automation_cases" in self.project_config:
            return self.project_config["automation_cases"].get(config_key, [])
        return []

    def add_scene_mapping(self, mapping_name: str, file_path: str, copy_to_project: bool = True) -> bool:
        """
        添加场景映射表到项目
        
        Args:
            mapping_name: 映射表名称
            file_path: Excel文件路径
            copy_to_project: 是否复制到项目目录
            
        Returns:
            bool: 是否添加成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            excel_file = Path(file_path)
            if not excel_file.exists():
                print(f"Excel文件不存在: {file_path}")
                return False
            
            if copy_to_project:
                # 复制到项目的Scene目录
                target_dir = self.current_project_path / "Scene"
                # 确保目录存在
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / excel_file.name
                shutil.copy2(excel_file, target_path)
                relative_path = f"Scene/{excel_file.name}"
            else:
                relative_path = str(excel_file)
            
            # 更新项目配置
            if "scene_mappings" not in self.project_config:
                self.project_config["scene_mappings"] = []
            
            mapping_info = {
                "name": mapping_name,
                "file": relative_path,
                "created_time": datetime.now().isoformat()
            }
            
            # 检查是否已存在
            existing_mappings = [m for m in self.project_config["scene_mappings"] if m["name"] == mapping_name]
            if existing_mappings:
                # 更新现有映射表
                idx = self.project_config["scene_mappings"].index(existing_mappings[0])
                self.project_config["scene_mappings"][idx] = mapping_info
            else:
                # 添加新映射表
                self.project_config["scene_mappings"].append(mapping_info)
            
            return self.save_project()
        except Exception as e:
            print(f"添加场景映射表失败: {e}")
            return False
    
    def get_scene_mappings(self) -> List[Dict[str, Any]]:
        """获取项目中的场景映射表列表"""
        return self.project_config.get("scene_mappings", [])
    
    def load_scene_mapping(self, mapping_name: str) -> Optional[Path]:
        """
        获取场景映射表文件路径
        
        Args:
            mapping_name: 映射表名称
            
        Returns:
            映射表文件路径，如果加载失败则返回None
        """
        if not self.current_project_path:
            return None
        
        try:
            # 从配置中查找映射表
            mapping_info = None
            for m in self.project_config.get("scene_mappings", []):
                if m["name"] == mapping_name:
                    mapping_info = m
                    break
            
            if not mapping_info:
                return None
            
            # 获取文件路径
            relative_path = mapping_info["file"]
            if Path(relative_path).is_absolute():
                return Path(relative_path)
            else:
                return self.current_project_path / relative_path
        except Exception as e:
            print(f"加载场景映射表失败: {e}")
            return None
    
    def delete_scene_mapping(self, mapping_name: str) -> bool:
        """
        删除场景映射表
        
        Args:
            mapping_name: 映射表名称
            
        Returns:
            bool: 是否删除成功
        """
        if not self.current_project_path:
            return False
        
        try:
            # 从配置中查找映射表
            mapping_info = None
            for m in self.project_config.get("scene_mappings", []):
                if m["name"] == mapping_name:
                    mapping_info = m
                    break
            
            if mapping_info:
                # 删除文件
                relative_path = mapping_info["file"]
                if not Path(relative_path).is_absolute():
                    file_path = self.current_project_path / relative_path
                    if file_path.exists():
                        file_path.unlink()
            
            # 从配置中移除
            if "scene_mappings" in self.project_config:
                self.project_config["scene_mappings"] = [
                    m for m in self.project_config["scene_mappings"]
                    if m["name"] != mapping_name
                ]
            
            return self.save_project()
        except Exception as e:
            print(f"删除场景映射表失败: {e}")
            return False

    # ==================== 测试需求文档相关方法 ====================

    def get_test_requirements(self) -> List[Dict[str, Any]]:
        """获取测试需求文档列表"""
        return self.project_config.get("test_requirements", [])

    def add_test_requirement(self, name: str, file_path: str, copy_to_project: bool = True) -> Tuple[bool, str]:
        """
        添加测试需求文档到项目

        Args:
            name: 文档名称
            file_path: 文档文件路径
            copy_to_project: 是否复制到项目目录

        Returns:
            Tuple[bool, str]: (是否添加成功, 错误消息)
        """
        if not self.current_project_path:
            return False, "没有打开的项目"

        try:
            source_file = Path(file_path)
            if not source_file.exists():
                return False, f"文件不存在: {file_path}"

            if copy_to_project:
                # 复制到项目的 TestRequirements 目录
                target_dir = self.current_project_path / "TestRequirements"
                target_dir.mkdir(parents=True, exist_ok=True)

                # 使用用户指定的名称作为目标文件名，避免同一文件不同名称导致覆盖
                file_suffix = source_file.suffix  # 保留原始扩展名
                target_filename = f"{name}{file_suffix}"

                # 如果目标文件名已存在，添加序号后缀
                target_path = target_dir / target_filename
                counter = 1
                while target_path.exists():
                    target_filename = f"{name}_{counter}{file_suffix}"
                    target_path = target_dir / target_filename
                    counter += 1

                shutil.copy2(source_file, target_path)
                relative_path = f"TestRequirements/{target_filename}"
            else:
                relative_path = str(source_file)

            # 更新项目配置
            if "test_requirements" not in self.project_config:
                self.project_config["test_requirements"] = []

            # 检查是否已存在同名文档
            for req in self.project_config["test_requirements"]:
                if req["name"] == name:
                    return False, f"测试需求文档 '{name}' 已存在，请使用其他名称"

            self.project_config["test_requirements"].append({
                "name": name,
                "file": relative_path
            })

            success = self.save_project()
            return success, "" if success else "保存项目配置失败"
        except Exception as e:
            return False, f"添加测试需求文档失败: {e}"

    def load_test_requirement(self, name: str) -> Optional[Path]:
        """
        获取测试需求文档的完整路径

        Args:
            name: 文档名称

        Returns:
            Path: 文档完整路径，如果不存在返回 None
        """
        if not self.current_project_path:
            return None

        for req in self.project_config.get("test_requirements", []):
            if req["name"] == name:
                relative_path = req["file"]
                if Path(relative_path).is_absolute():
                    return Path(relative_path)
                else:
                    return self.current_project_path / relative_path

        return None

    def delete_test_requirement(self, name: str) -> bool:
        """
        删除测试需求文档

        Args:
            name: 文档名称

        Returns:
            bool: 是否删除成功
        """
        if not self.current_project_path:
            return False

        try:
            # 查找文档信息
            req_info = None
            for req in self.project_config.get("test_requirements", []):
                if req["name"] == name:
                    req_info = req
                    break

            if req_info:
                # 删除文件（如果在项目目录内）
                relative_path = req_info["file"]
                if not Path(relative_path).is_absolute():
                    file_path = self.current_project_path / relative_path
                    if file_path.exists():
                        file_path.unlink()

            # 从配置中移除
            if "test_requirements" in self.project_config:
                self.project_config["test_requirements"] = [
                    req for req in self.project_config["test_requirements"]
                    if req["name"] != name
                ]

            return self.save_project()
        except Exception as e:
            print(f"删除测试需求文档失败: {e}")
            return False

    # ==================== Test Results 相关方法 ====================

    def get_test_results_directory_structure(self, data_type: str) -> Dict[str, Any]:
        """
        获取 Test Results 目录结构

        Args:
            data_type: "trace_data" 或 "record_data"

        Returns:
            目录结构字典
        """
        if not self.current_project_path:
            return {}

        def build_tree(path: Path, relative_path: str = "") -> Dict[str, Any]:
            """递归构建目录树"""
            node = {
                "name": path.name,
                "type": "directory" if path.is_dir() else "file",
                "path": relative_path,
                "children": []
            }

            if path.is_dir():
                items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
                for item in items:
                    item_relative = f"{relative_path}/{item.name}" if relative_path else item.name
                    node["children"].append(build_tree(item, item_relative))

            return node

        # data_type 对应的目录名
        DATA_TYPE_DIR_MAP = {
            "trace_data": "trace data",
            "record_data": "record data",
            "log_data": "log data",
            "report_data": "report data"
        }
        dir_name = DATA_TYPE_DIR_MAP.get(data_type, "trace data")
        case_dir = self.current_project_path / "Test Results" / dir_name
        if not case_dir.exists():
            return {
                "name": "",
                "type": "directory",
                "path": "",
                "children": []
            }

        result = {
            "name": "",
            "type": "directory",
            "path": "",
            "children": []
        }

        items = sorted(case_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        for item in items:
            result["children"].append(build_tree(item, item.name))

        return result

    def sync_test_results(self) -> bool:
        """
        同步 test_results 目录结构到 project.json
        扫描 trace data、record data、log data、report data 目录，更新配置中的列表

        Returns:
            bool: 是否同步成功
        """
        if not self.current_project_path:
            print("没有打开的项目")
            return False

        try:
            # 确保 test_results 配置存在
            if "test_results" not in self.project_config:
                self.project_config["test_results"] = {
                    "trace_data": [],
                    "record_data": [],
                    "log_data": [],
                    "report_data": []
                }

            # data_type -> (dir_name, file_ext)
            data_type_map = {
                "trace_data": ("trace data", ".blf"),
                "record_data": ("record data", ".record"),
                "log_data": ("log data", ".log"),
                "report_data": ("report data", ".html")
            }

            for data_type, (dir_name, ext) in data_type_map.items():
                case_dir = self.current_project_path / "Test Results" / dir_name
                cases_list = []

                if case_dir.exists():
                    # 遍历目录，收集所有文件
                    for file_path in case_dir.rglob(f"*{ext}"):
                        relative_path = file_path.relative_to(case_dir)
                        directory = str(relative_path.parent) if relative_path.parent != Path(".") else ""

                        case_info = {
                            "name": file_path.stem,
                            "file": f"Test Results/{dir_name}/{relative_path.as_posix()}",
                            "directory": directory,
                            "modified_time": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                        }
                        cases_list.append(case_info)

                self.project_config["test_results"][data_type] = cases_list

            return self.save_project()
        except Exception as e:
            print(f"同步 test_results 失败: {e}")
            return False

    def add_test_results_item(self, item_name: str, data_type: str, directory: str = "") -> bool:
        """
        添加 test_results 项目到配置

        Args:
            item_name: 项目名称
            data_type: "trace" 或 "record"
            directory: 目录路径（相对于 trace data 或 record data 目录）

        Returns:
            bool: 是否添加成功
        """
        if not self.current_project_path:
            return False

        try:
            config_key = f"{data_type}_data"
            if "test_results" not in self.project_config:
                self.project_config["test_results"] = {"trace_data": [], "record_data": []}

            dir_name = "trace data" if config_key == "trace_data" else "record data"
            ext = ".blf" if data_type == "trace" else ".record"
            relative_path = f"Test Results/{dir_name}/{directory}/{item_name}{ext}" if directory else f"Test Results/{dir_name}/{item_name}{ext}"
            relative_path = relative_path.replace("//", "/")

            item_info = {
                "name": item_name,
                "file": relative_path,
                "directory": directory,
                "created_time": datetime.now().isoformat()
            }

            # 检查是否已存在
            existing_items = [c for c in self.project_config["test_results"][config_key]
                            if c["name"] == item_name and c.get("directory", "") == directory]
            if existing_items:
                idx = self.project_config["test_results"][config_key].index(existing_items[0])
                self.project_config["test_results"][config_key][idx] = item_info
            else:
                self.project_config["test_results"][config_key].append(item_info)

            return self.save_project()
        except Exception as e:
            print(f"添加 test_results 项目失败: {e}")
            return False

    def remove_test_results_item(self, item_name: str, data_type: str, directory: str = "") -> bool:
        """
        从配置中移除 test_results 项目

        Args:
            item_name: 项目名称
            data_type: "trace" 或 "record"
            directory: 目录路径

        Returns:
            bool: 是否移除成功
        """
        if not self.current_project_path:
            return False

        try:
            config_key = f"{data_type}_data"
            if "test_results" in self.project_config and config_key in self.project_config["test_results"]:
                self.project_config["test_results"][config_key] = [
                    c for c in self.project_config["test_results"][config_key]
                    if not (c["name"] == item_name and c.get("directory", "") == directory)
                ]
                return self.save_project()
            return True
        except Exception as e:
            print(f"移除 test_results 项目失败: {e}")
            return False

    def get_test_results_items(self, data_type: str) -> List[Dict[str, Any]]:
        """
        获取指定类型的 test_results 项目列表

        Args:
            data_type: "trace" 或 "record"

        Returns:
            test_results 项目列表
        """
        config_key = f"{data_type}_data"
        if "test_results" in self.project_config:
            return self.project_config["test_results"].get(config_key, [])
        return []
