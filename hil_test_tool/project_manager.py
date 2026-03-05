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

            for subdir in canoe_subdirs + simulink_subdirs + dsl_subdirs + automation_subdirs + scene_subdirs:
                (project_dir / subdir).mkdir(parents=True, exist_ok=True)
            
            # 创建项目配置文件
            project_config = {
                "project_name": project_name,
                "created_time": datetime.now().isoformat(),
                "modified_time": datetime.now().isoformat(),
                "version": "1.0.0",
                "canoe": {
                    "dbc_files": [],
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
                "test_requirements": []
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
                target_dir = self.current_project_path / "CANoe" / "dbc_file"
                target_path = target_dir / dbc_file.name
                shutil.copy2(dbc_file, target_path)
                relative_path = f"CANoe/dbc_file/{dbc_file.name}"
            else:
                relative_path = str(dbc_file)
            
            if "canoe" not in self.project_config:
                self.project_config["canoe"] = {}
            if "dbc_files" not in self.project_config["canoe"]:
                self.project_config["canoe"]["dbc_files"] = []
            
            if relative_path not in self.project_config["canoe"]["dbc_files"]:
                self.project_config["canoe"]["dbc_files"].append(relative_path)
            
            return self.save_project()
        except Exception as e:
            print(f"添加DBC文件失败: {e}")
            return False
    
    def add_env_dbc_file(self, dbc_path: str, copy_to_project: bool = True) -> bool:
        """
        添加环境变量DBC文件到项目
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
                target_dir = self.current_project_path / "CANoe" / "env_dbc"
                target_path = target_dir / dbc_file.name
                shutil.copy2(dbc_file, target_path)
                relative_path = f"CANoe/env_dbc/{dbc_file.name}"
            else:
                relative_path = str(dbc_file)
            
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
                target_dir = self.current_project_path / "CANoe" / "system_variable"
                target_path = target_dir / var_file.name
                shutil.copy2(var_file, target_path)
                relative_path = f"CANoe/system_variable/{var_file.name}"
            else:
                relative_path = str(var_file)
            
            if "canoe" not in self.project_config:
                self.project_config["canoe"] = {}
            if "system_variable_files" not in self.project_config["canoe"]:
                self.project_config["canoe"]["system_variable_files"] = []
            
            if relative_path not in self.project_config["canoe"]["system_variable_files"]:
                self.project_config["canoe"]["system_variable_files"].append(relative_path)
            
            return self.save_project()
        except Exception as e:
            print(f"添加系统变量文件失败: {e}")
            return False
    
    def remove_dbc_file(self, file_name: str) -> bool:
        """删除DBC文件"""
        if not self.current_project_path:
            return False
        
        try:
            file_dir = self.current_project_path / "CANoe" / "dbc_file"
            file_path = file_dir / file_name
            
            if file_path.exists():
                file_path.unlink()
            
            if "canoe" in self.project_config and "dbc_files" in self.project_config["canoe"]:
                self.project_config["canoe"]["dbc_files"] = [
                    f for f in self.project_config["canoe"]["dbc_files"]
                    if not f.endswith(file_name)
                ]
            
            return self.save_project()
        except Exception as e:
            print(f"删除DBC文件失败: {e}")
            return False
    
    def remove_env_dbc_file(self, file_name: str) -> bool:
        """删除环境变量DBC文件"""
        if not self.current_project_path:
            return False
        
        try:
            file_dir = self.current_project_path / "CANoe" / "env_dbc"
            file_path = file_dir / file_name
            
            if file_path.exists():
                file_path.unlink()
            
            if "canoe" in self.project_config and "env_dbc_files" in self.project_config["canoe"]:
                self.project_config["canoe"]["env_dbc_files"] = [
                    f for f in self.project_config["canoe"]["env_dbc_files"]
                    if not f.endswith(file_name)
                ]
            
            return self.save_project()
        except Exception as e:
            print(f"删除环境变量DBC文件失败: {e}")
            return False
    
    def remove_system_variable_file(self, file_name: str) -> bool:
        """删除系统变量文件"""
        if not self.current_project_path:
            return False
        
        try:
            file_dir = self.current_project_path / "CANoe" / "system_variable"
            file_path = file_dir / file_name
            
            if file_path.exists():
                file_path.unlink()
            
            if "canoe" in self.project_config and "system_variable_files" in self.project_config["canoe"]:
                self.project_config["canoe"]["system_variable_files"] = [
                    f for f in self.project_config["canoe"]["system_variable_files"]
                    if not f.endswith(file_name)
                ]
            
            return self.save_project()
        except Exception as e:
            print(f"删除系统变量文件失败: {e}")
            return False
    
    def set_can_channel_mapping(self, mapping: Dict[str, int]) -> bool:
        """设置CAN通道映射关系"""
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            if "canoe" not in self.project_config:
                self.project_config["canoe"] = {}
            self.project_config["canoe"]["can_channel_mapping"] = mapping
            
            mapping_dir = self.current_project_path / "CANoe" / "mapping_file"
            mapping_file = mapping_dir / "can_channel_mapping.json"
            
            formatted_mapping = {}
            for dbc_path, channel in mapping.items():
                dbc_name = Path(dbc_path).name
                formatted_mapping[dbc_name] = channel
            
            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(formatted_mapping, f, indent=4, ensure_ascii=False)
            
            return self.save_project()
        except Exception as e:
            print(f"设置CAN通道映射失败: {e}")
            return False
    
    def get_can_channel_mapping(self) -> Dict[str, int]:
        """获取CAN通道映射关系（返回绝对路径的映射）"""
        relative_mapping = self.project_config.get("canoe", {}).get("can_channel_mapping", {})
        if not self.current_project_path:
            return relative_mapping
        absolute_mapping = {}
        for rel_path, channel in relative_mapping.items():
            abs_path = str(self.current_project_path / rel_path)
            absolute_mapping[abs_path] = channel
        return absolute_mapping
    
    def get_dbc_files(self) -> List[str]:
        """获取项目中的DBC文件列表（返回绝对路径）"""
        relative_paths = self.project_config.get("canoe", {}).get("dbc_files", [])
        if not self.current_project_path:
            return relative_paths
        absolute_paths = []
        for rel_path in relative_paths:
            abs_path = self.current_project_path / rel_path
            absolute_paths.append(str(abs_path))
        return absolute_paths
    
    def get_env_dbc_files(self) -> List[str]:
        """获取项目中的环境变量DBC文件列表（返回绝对路径）"""
        relative_paths = self.project_config.get("canoe", {}).get("env_dbc_files", [])
        if not self.current_project_path:
            return relative_paths
        absolute_paths = []
        for rel_path in relative_paths:
            abs_path = self.current_project_path / rel_path
            absolute_paths.append(str(abs_path))
        return absolute_paths
    
    def get_system_variable_files(self) -> List[str]:
        """获取项目中的系统变量文件列表"""
        return self.project_config.get("canoe", {}).get("system_variable_files", [])
    
    def set_canoe_project_path(self, project_path: str) -> bool:
        """设置CANoe工程文件地址"""
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
        """添加Simulink文件到项目"""
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            file = Path(file_path)
            if not file.exists():
                print(f"文件不存在: {file_path}")
                return False
            
            if copy_to_project:
                target_dir = self.current_project_path / "Simulink" / "project_info"
                target_path = target_dir / file.name
                shutil.copy2(file, target_path)
                relative_path = f"Simulink/project_info/{file.name}"
            else:
                relative_path = str(file)
            
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
            
            existing_files = [f for f in self.project_config["simulink"]["files"] if f["name"] == file.name]
            if existing_files:
                idx = self.project_config["simulink"]["files"].index(existing_files[0])
                self.project_config["simulink"]["files"][idx] = file_info
            else:
                self.project_config["simulink"]["files"].append(file_info)
            
            return self.save_project()
        except Exception as e:
            print(f"添加Simulink文件失败: {e}")
            return False
    
    def get_simulink_files(self) -> List[Dict[str, Any]]:
        """获取项目中的Simulink文件列表"""
        return self.project_config.get("simulink", {}).get("files", [])
    
    def get_full_path(self, relative_path: str) -> Optional[Path]:
        """获取相对路径的完整路径"""
        if not self.current_project_path:
            return None
        
        if Path(relative_path).is_absolute():
            return Path(relative_path)
        
        return self.current_project_path / relative_path
    
    def add_dsl_case(self, case_name: str, case_content: str, directory: str = "") -> bool:
        """添加DSL case到项目"""
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            case_dir = self.current_project_path / "dsl_case"
            if directory:
                case_dir = case_dir / directory
            
            case_dir.mkdir(parents=True, exist_ok=True)
            
            case_file = case_dir / f"{case_name}.dsl"
            
            with open(case_file, 'w', encoding='utf-8') as f:
                f.write(case_content)
            
            if "dsl_cases" not in self.project_config:
                self.project_config["dsl_cases"] = []
            
            relative_path = f"dsl_case/{directory}/{case_name}.dsl" if directory else f"dsl_case/{case_name}.dsl"
            
            case_info = {
                "name": case_name,
                "file": relative_path,
                "directory": directory,
                "created_time": datetime.now().isoformat()
            }
            
            existing_cases = [c for c in self.project_config["dsl_cases"] if c["name"] == case_name and c.get("directory", "") == directory]
            if existing_cases:
                idx = self.project_config["dsl_cases"].index(existing_cases[0])
                self.project_config["dsl_cases"][idx] = case_info
            else:
                self.project_config["dsl_cases"].append(case_info)
            
            return self.save_project()
        except Exception as e:
            print(f"添加DSL case失败: {e}")
            return False
    
    def get_dsl_cases(self) -> List[Dict[str, Any]]:
        """获取项目中的DSL case列表"""
        return self.project_config.get("dsl_cases", [])
    
    def load_dsl_case(self, case_name: str, directory: str = "") -> Optional[str]:
        """加载DSL case内容"""
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
        """删除DSL case"""
        if not self.current_project_path:
            return False
        
        try:
            case_dir = self.current_project_path / "dsl_case"
            if directory:
                case_dir = case_dir / directory
            
            case_file = case_dir / f"{case_name}.dsl"
            
            if case_file.exists():
                case_file.unlink()
            
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
        """创建DSL case目录"""
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
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
        """删除DSL case目录及其内容"""
        if not self.current_project_path:
            return False
        
        try:
            case_dir = self.current_project_path / "dsl_case"
            target_dir = case_dir / directory
            
            if target_dir.exists() and target_dir.is_dir():
                shutil.rmtree(target_dir)
            
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
        """重命名DSL case文件"""
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            case_dir = self.current_project_path / "dsl_case"
            if directory:
                case_dir = case_dir / directory
            
            old_file = case_dir / f"{old_case_name}.dsl"
            new_file = case_dir / f"{new_case_name}.dsl"
            
            if not old_file.exists():
                print(f"文件不存在: {old_file}")
                return False
            
            if new_file.exists():
                print(f"文件已存在: {new_file}")
                return False
            
            old_file.rename(new_file)
            
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
        """重命名DSL case目录"""
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            case_dir = self.current_project_path / "dsl_case"
            old_dir_path = case_dir / old_directory
            
            if not old_dir_path.exists() or not old_dir_path.is_dir():
                print(f"目录不存在: {old_directory}")
                return False
            
            parent_path = old_dir_path.parent
            new_dir_path = parent_path / new_directory_name
            
            if new_dir_path.exists():
                print(f"目录已存在: {new_directory_name}")
                return False
            
            old_dir_path.rename(new_dir_path)
            
            if "/" in old_directory:
                parts = old_directory.split("/")
                parts[-1] = new_directory_name
                new_directory = "/".join(parts)
            else:
                new_directory = new_directory_name
            
            if "dsl_cases" in self.project_config:
                for case_info in self.project_config["dsl_cases"]:
                    old_dir = case_info.get("directory", "")
                    if old_dir == old_directory or old_dir.startswith(old_directory + "/"):
                        if old_dir == old_directory:
                            case_info["directory"] = new_directory
                        else:
                            suffix = old_dir[len(old_directory):]
                            case_info["directory"] = new_directory + suffix
                        
                        case_name = case_info["name"]
                        case_info["file"] = f"dsl_case/{case_info['directory']}/{case_name}.dsl"
            
            return self.save_project()
        except Exception as e:
            print(f"重命名DSL目录失败: {e}")
            return False
    
    def copy_dsl_case(self, case_name: str, new_case_name: str, directory: str = "") -> bool:
        """复制DSL case文件"""
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            case_dir = self.current_project_path / "dsl_case"
            if directory:
                case_dir = case_dir / directory
            
            old_file = case_dir / f"{case_name}.dsl"
            new_file = case_dir / f"{new_case_name}.dsl"
            
            if not old_file.exists():
                print(f"文件不存在: {old_file}")
                return False
            
            final_name = new_case_name
            while new_file.exists():
                final_name = f"{final_name}_copy"
                new_file = case_dir / f"{final_name}.dsl"
            
            shutil.copy2(old_file, new_file)
            
            if "dsl_cases" not in self.project_config:
                self.project_config["dsl_cases"] = []
            
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
        """复制DSL case目录及其内容"""
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            case_dir = self.current_project_path / "dsl_case"
            old_dir_path = case_dir / directory
            
            if not old_dir_path.exists() or not old_dir_path.is_dir():
                print(f"目录不存在: {directory}")
                return False
            
            parent_path = old_dir_path.parent
            new_dir_path = parent_path / new_directory_name
            
            final_name = new_directory_name
            while new_dir_path.exists():
                final_name = f"{final_name}_copy"
                new_dir_path = parent_path / final_name
            
            shutil.copytree(old_dir_path, new_dir_path)
            
            if "/" in directory:
                parts = directory.split("/")
                parts[-1] = final_name
                new_directory = "/".join(parts)
            else:
                new_directory = final_name
            
            if "dsl_cases" not in self.project_config:
                self.project_config["dsl_cases"] = []
            
            for dsl_file in new_dir_path.rglob("*.dsl"):
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
        """获取DSL case目录结构"""
        if not self.current_project_path:
            return {}
        
        def build_tree(path: Path, relative_path: str = "") -> Dict[str, Any]:
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
        
        case_dir = self.current_project_path / "dsl_case"
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

    def get_automation_directory_structure(self, case_type: str) -> Dict[str, Any]:
        """获取Automation Cases目录结构"""
        if not self.current_project_path:
            return {}

        def build_tree(path: Path, relative_path: str = "") -> Dict[str, Any]:
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
        """同步 dsl_cases 目录结构到 project.json"""
        if not self.current_project_path:
            print("没有打开的项目")
            return False

        try:
            dsl_dir = self.current_project_path / "dsl_case"
            cases_list = []

            if dsl_dir.exists():
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
        """同步 automation_cases 目录结构到 project.json"""
        if not self.current_project_path:
            print("没有打开的项目")
            return False

        try:
            if "automation_cases" not in self.project_config:
                self.project_config["automation_cases"] = {
                    "py_cases": [],
                    "json_cases": []
                }

            for case_type in ["py_cases", "json_cases"]:
                case_dir = self.current_project_path / "automation_case" / case_type
                cases_list = []

                if case_dir.exists():
                    ext = ".py" if case_type == "py_cases" else ".json"

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
        """添加 automation case 到配置"""
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
        """从配置中移除 automation case"""
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
        """在配置中重命名 automation case"""
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
        """获取指定类型的 automation cases 列表"""
        config_key = f"{case_type}_cases"
        if "automation_cases" in self.project_config:
            return self.project_config["automation_cases"].get(config_key, [])
        return []

    def add_scene_mapping(self, mapping_name: str, file_path: str, copy_to_project: bool = True) -> bool:
        """添加场景映射表到项目"""
        if not self.current_project_path:
            print("没有打开的项目")
            return False
        
        try:
            excel_file = Path(file_path)
            if not excel_file.exists():
                print(f"Excel文件不存在: {file_path}")
                return False
            
            if copy_to_project:
                target_dir = self.current_project_path / "Scene"
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / excel_file.name
                shutil.copy2(excel_file, target_path)
                relative_path = f"Scene/{excel_file.name}"
            else:
                relative_path = str(excel_file)
            
            if "scene_mappings" not in self.project_config:
                self.project_config["scene_mappings"] = []
            
            mapping_info = {
                "name": mapping_name,
                "file": relative_path,
                "created_time": datetime.now().isoformat()
            }
            
            existing_mappings = [m for m in self.project_config["scene_mappings"] if m["name"] == mapping_name]
            if existing_mappings:
                idx = self.project_config["scene_mappings"].index(existing_mappings[0])
                self.project_config["scene_mappings"][idx] = mapping_info
            else:
                self.project_config["scene_mappings"].append(mapping_info)
            
            return self.save_project()
        except Exception as e:
            print(f"添加场景映射表失败: {e}")
            return False
    
    def get_scene_mappings(self) -> List[Dict[str, Any]]:
        """获取项目中的场景映射表列表"""
        return self.project_config.get("scene_mappings", [])
    
    def load_scene_mapping(self, mapping_name: str) -> Optional[Path]:
        """获取场景映射表文件路径"""
        if not self.current_project_path:
            return None
        
        try:
            mapping_info = None
            for m in self.project_config.get("scene_mappings", []):
                if m["name"] == mapping_name:
                    mapping_info = m
                    break
            
            if not mapping_info:
                return None
            
            relative_path = mapping_info["file"]
            if Path(relative_path).is_absolute():
                return Path(relative_path)
            else:
                return self.current_project_path / relative_path
        except Exception as e:
            print(f"加载场景映射表失败: {e}")
            return None
    
    def delete_scene_mapping(self, mapping_name: str) -> bool:
        """删除场景映射表"""
        if not self.current_project_path:
            return False
        
        try:
            mapping_info = None
            for m in self.project_config.get("scene_mappings", []):
                if m["name"] == mapping_name:
                    mapping_info = m
                    break
            
            if mapping_info:
                relative_path = mapping_info["file"]
                if not Path(relative_path).is_absolute():
                    file_path = self.current_project_path / relative_path
                    if file_path.exists():
                        file_path.unlink()
            
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
        """添加测试需求文档到项目"""
        if not self.current_project_path:
            return False, "没有打开的项目"

        try:
            source_file = Path(file_path)
            if not source_file.exists():
                return False, f"文件不存在: {file_path}"

            if copy_to_project:
                target_dir = self.current_project_path / "TestRequirements"
                target_dir.mkdir(parents=True, exist_ok=True)

                file_suffix = source_file.suffix
                target_filename = f"{name}{file_suffix}"

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

            if "test_requirements" not in self.project_config:
                self.project_config["test_requirements"] = []

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
        """获取测试需求文档的完整路径"""
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
        """删除测试需求文档"""
        if not self.current_project_path:
            return False

        try:
            req_info = None
            for req in self.project_config.get("test_requirements", []):
                if req["name"] == name:
                    req_info = req
                    break

            if req_info:
                relative_path = req_info["file"]
                if not Path(relative_path).is_absolute():
                    file_path = self.current_project_path / relative_path
                    if file_path.exists():
                        file_path.unlink()

            if "test_requirements" in self.project_config:
                self.project_config["test_requirements"] = [
                    req for req in self.project_config["test_requirements"]
                    if req["name"] != name
                ]

            return self.save_project()
        except Exception as e:
            print(f"删除测试需求文档失败: {e}")
            return False
