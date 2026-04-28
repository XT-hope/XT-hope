"""
DBC解析器模块
负责解析DBC文件，提取信号、消息等信息，用于智能提示和补全
"""
import cantools
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any


class DBCParser:
    """DBC文件解析器"""
    
    def __init__(self):
        self.dbc_files: Dict[str, cantools.database.Database] = {}
        self.env_dbc_files: Dict[str, cantools.database.Database] = {}
        self.can_channel_mapping: Dict[str, Dict] = {}
        self.system_variables: Set[str] = set()
        # 存储struct定义信息：{struct_full_path: {"members": [member_names], "variable_type": variable_type}}
        self.struct_definitions: Dict[str, Dict[str, Any]] = {}
        # 存储变量到struct的映射：{variable_full_path: struct_full_path}
        self.variable_to_struct: Dict[str, str] = {}
    
    def load_dbc_file(self, dbc_path: str, file_type: str = "normal") -> bool:
        """
        加载DBC文件
        
        Args:
            dbc_path: DBC文件路径
            file_type: 文件类型 ("normal" 或 "env")
            
        Returns:
            bool: 是否加载成功
        """
        try:
            db = cantools.database.load_file(dbc_path)
            
            if file_type == "normal":
                self.dbc_files[dbc_path] = db
            elif file_type == "env":
                self.env_dbc_files[dbc_path] = db
            
            return True
        except Exception as e:
            print(f"加载DBC文件失败 {dbc_path}: {e}")
            return False
    
    def unload_dbc_file(self, dbc_path: str) -> None:
        """卸载DBC文件"""
        if dbc_path in self.dbc_files:
            del self.dbc_files[dbc_path]
        if dbc_path in self.env_dbc_files:
            del self.env_dbc_files[dbc_path]
    
    def set_can_channel_mapping(self, mapping: Dict[str, Dict]) -> None:
        """
        设置CAN通道映射

        Args:
            mapping: 格式 {dbc_path: {"channel": int, "short_name": str}}
        """
        self.can_channel_mapping = mapping
    
    def load_system_variables(self, file_path: str) -> bool:
        """
        加载系统变量文件

        Args:
            file_path: 系统变量文件路径

        Returns:
            bool: 是否加载成功
        """
        # 先检查文件是否存在
        if not Path(file_path).exists():
            return False

        # 尝试多种编码读取文件
        content = None
        for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-16', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if content is None:
            print(f"无法解码系统变量文件: {file_path}")
            return False

        try:
            # 尝试解析XML格式的系统变量文件
            if '<systemvariables>' in content or '<namespace' in content:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(content)

                # 先解析所有struct定义
                self._parse_struct_definitions(root, "")

                # 递归解析namespace和variable
                self._parse_namespace(root, "")
            else:
                # 尝试解析其他格式（如简单的文本格式）
                # 假设每行一个系统变量，格式为：namespace::variable 或 variable
                lines = content.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#'):  # 跳过空行和注释
                        # 移除可能的行尾注释
                        if '#' in line:
                            line = line.split('#')[0].strip()
                        if line:
                            self.system_variables.add(line)

            return True
        except Exception as e:
            print(f"加载系统变量文件失败: {e}")
            return False
    
    def _parse_struct_definitions(self, element: 'ET.Element', parent_path: str) -> None:
        """
        递归解析struct定义
        
        Args:
            element: XML元素
            parent_path: 父namespace路径
        """
        import xml.etree.ElementTree as ET
        
        # 查找当前元素下的直接子namespace（不包括后代）
        for namespace in element.findall('./namespace'):
            namespace_name = namespace.get('name', '')
            
            # 构建当前namespace的完整路径
            if namespace_name:
                if parent_path:
                    current_path = f"{parent_path}::{namespace_name}"
                else:
                    current_path = namespace_name
            else:
                current_path = parent_path
            
            # 查找当前namespace下的直接子struct（不包括后代）
            for struct in namespace.findall('./struct'):
                struct_name = struct.get('name', '')
                
                if struct_name:
                    # 构建完整的struct路径
                    if current_path:
                        full_struct_path = f"{current_path}::{struct_name}"
                    else:
                        full_struct_path = struct_name
                    
                    # 解析struct成员
                    members = []
                    for member in struct.findall('./structMember'):
                        member_name = member.get('name', '')
                        if member_name:
                            members.append(member_name)
                    
                    # 存储struct定义
                    self.struct_definitions[full_struct_path] = {
                        "members": members,
                        "variable_type": struct_name
                    }
            
            # 递归解析子namespace
            self._parse_struct_definitions(namespace, current_path)
    
    def _parse_namespace(self, element: 'ET.Element', parent_path: str) -> None:
        """
        递归解析namespace和variable
        
        Args:
            element: XML元素
            parent_path: 父namespace路径
        """
        import xml.etree.ElementTree as ET
        
        # 查找当前元素下的直接子namespace（不包括后代）
        for namespace in element.findall('./namespace'):
            namespace_name = namespace.get('name', '')
            
            # 构建当前namespace的完整路径
            if namespace_name:
                if parent_path:
                    current_path = f"{parent_path}::{namespace_name}"
                else:
                    current_path = namespace_name
            else:
                current_path = parent_path
            
            # 查找当前namespace下的直接子variable（不包括后代）
            for variable in namespace.findall('./variable'):
                var_name = variable.get('name', '')
                var_type = variable.get('type', '')
                struct_def = variable.get('structDefinition', '')
                
                if var_name:
                    # 构建完整的系统变量路径
                    if current_path:
                        full_var_name = f"{current_path}::{var_name}"
                    else:
                        full_var_name = var_name
                    
                    # 添加变量
                    self.system_variables.add(full_var_name)
                    
                    # 如果是struct类型，记录变量到struct的映射
                    if var_type == 'struct' and struct_def:
                        self.variable_to_struct[full_var_name] = struct_def
            
            # 递归解析子namespace
            self._parse_namespace(namespace, current_path)
    
    def get_system_variables(self) -> List[str]:
        """获取所有系统变量"""
        return list(self.system_variables)
    
    def get_can_channel_for_dbc(self, dbc_path: str) -> Optional[int]:
        """
        获取DBC文件对应的CAN通道

        Args:
            dbc_path: DBC文件路径

        Returns:
            CAN通道号，如果未找到则返回None
        """
        mapping_info = self.can_channel_mapping.get(dbc_path)
        if mapping_info is None:
            # 尝试使用 Path 规范化路径进行比较
            from pathlib import Path
            dbc_path_normalized = str(Path(dbc_path).resolve())
            for mapping_path, info in self.can_channel_mapping.items():
                if str(Path(mapping_path).resolve()) == dbc_path_normalized:
                    mapping_info = info
                    break

        if mapping_info is None:
            return None
        # 兼容新旧格式
        if isinstance(mapping_info, dict):
            return mapping_info.get("channel")
        return mapping_info  # 旧格式直接返回int
    
    def get_signal_completion(self, prefix: str, signal_type: str = "sig") -> List[str]:
        """
        获取信号补全建议

        Args:
            prefix: 输入前缀
            signal_type: 信号类型 ("sig", "env", "sys")

        Returns:
            补全建议列表
        """
        suggestions = []
        if signal_type == "sig":
            # CAN信号补全: sig::CAN X::Message::Signal
            for dbc_path, db in self.dbc_files.items():
                channel = self.get_can_channel_for_dbc(dbc_path)
                if channel is None:
                    continue

                for msg in db.messages:
                    for sig in msg.signals:
                        # 构建完整的信号路径（channel+1 使 CAN 从 1 开始）
                        signal_path = f"sig::CAN {channel + 1}::{msg.name}::{sig.name}"
                        if signal_path.lower().startswith(prefix.lower()):
                            suggestions.append(signal_path)

        elif signal_type == "env":
            # 环境变量补全: env::CAN X::Message::Signal（来自DBC文件）
            for dbc_path, db in self.dbc_files.items():
                channel = self.get_can_channel_for_dbc(dbc_path)
                if channel is None:
                    continue

                for msg in db.messages:
                    for sig in msg.signals:
                        # 构建完整的环境变量路径（channel+1 使 CAN 从 1 开始）
                        env_path = f"env::CAN {channel + 1}::{msg.name}::{sig.name}"
                        if env_path.lower().startswith(prefix.lower()):
                            suggestions.append(env_path)
        
        elif signal_type == "sys":
            # 系统变量补全: sys::Variable 或 sys::Variable.member
            # 检查是否包含.，表示要补全struct成员
            if "." in prefix:
                # 分离变量路径和成员前缀
                var_part, member_prefix = prefix.rsplit(".", 1)
                var_path = var_part.replace("sys::", "", 1)
                
                # 查找变量对应的struct定义
                struct_def = self.variable_to_struct.get(var_path)
                if struct_def and struct_def in self.struct_definitions:
                    # 获取struct成员
                    members = self.struct_definitions[struct_def]["members"]
                    for member in members:
                        if member.lower().startswith(member_prefix.lower()):
                            suggestions.append(f"{var_part}.{member}")
            else:
                # 普通系统变量补全
                for var in self.system_variables:
                    sys_path = f"sys::{var}"
                    if sys_path.lower().startswith(prefix.lower()):
                        suggestions.append(sys_path)
        
        return sorted(suggestions)
    
    def _infer_channel_from_env_dbc(self, env_dbc_path: str) -> Optional[int]:
        """
        从环境变量DBC路径推断CAN通道

        Args:
            env_dbc_path: 环境变量DBC文件路径

        Returns:
            CAN通道号，如果无法推断则返回None
        """
        # 尝试从文件名中推断原始DBC
        # 例如: controlGenEnvironmentVariable.dbc -> Control DBC
        filename = Path(env_dbc_path).name.lower()

        # 查找匹配的原始DBC
        for dbc_path, mapping_info in self.can_channel_mapping.items():
            dbc_filename = Path(dbc_path).name.lower()

            # 兼容新旧格式
            if isinstance(mapping_info, dict):
                channel = mapping_info.get("channel")
            else:
                channel = mapping_info

            # 检查是否有共同的关键词
            if "control" in filename and "control" in dbc_filename:
                return channel
            elif "chassis" in filename and "chassis" in dbc_filename:
                return channel

        return None
    
    def clear(self) -> None:
        """清除所有加载的数据"""
        self.dbc_files.clear()
        self.env_dbc_files.clear()
        self.can_channel_mapping.clear()
        self.system_variables.clear()
        self.struct_definitions.clear()
    
    def remove_system_variables(self, file_path: str) -> None:
        """
        移除系统变量文件中的所有变量

        Args:
            file_path: 系统变量文件路径
        """
        # 先检查文件是否存在
        if not Path(file_path).exists():
            return

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 尝试解析XML格式的系统变量文件
            if '<systemvariables>' in content or '<namespace' in content:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(content)

                # 递归移除namespace和variable
                self._remove_namespace_variables(root, "")
            else:
                # 尝试解析其他格式（如简单的文本格式）
                lines = content.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # 移除可能的行尾注释
                        if '#' in line:
                            line = line.split('#')[0].strip()
                        if line:
                            self.system_variables.discard(line)
        except Exception as e:
            print(f"移除系统变量文件失败: {e}")
    
    def _remove_namespace_variables(self, element: 'ET.Element', parent_path: str) -> None:
        """
        递归移除namespace和variable
        
        Args:
            element: XML元素
            parent_path: 父namespace路径
        """
        import xml.etree.ElementTree as ET
        
        # 查找当前元素下的直接子namespace（不包括后代）
        for namespace in element.findall('./namespace'):
            namespace_name = namespace.get('name', '')
            
            # 构建当前namespace的完整路径
            if namespace_name:
                if parent_path:
                    current_path = f"{parent_path}::{namespace_name}"
                else:
                    current_path = namespace_name
            else:
                current_path = parent_path
            
            # 查找当前namespace下的直接子variable（不包括后代）
            for variable in namespace.findall('./variable'):
                var_name = variable.get('name', '')
                
                if var_name:
                    # 构建完整的系统变量路径
                    if current_path:
                        full_var_name = f"{current_path}::{var_name}"
                    else:
                        full_var_name = var_name
                    
                    # 移除变量
                    self.system_variables.discard(full_var_name)
                    
                    # 移除变量到struct的映射
                    if full_var_name in self.variable_to_struct:
                        del self.variable_to_struct[full_var_name]
            
            # 递归移除子namespace
            self._remove_namespace_variables(namespace, current_path)
        self.variable_to_struct.clear()
