# core/project_manager.py
import json
import os
import time
from datetime import datetime

class ProjectManager:
    """项目文件管理器，负责项目的创建、保存、加载和最近项目记录"""
    
    def __init__(self):
        self.current_project = None
        self.project_path = None
        self.recent_projects = self._load_recent_projects()
        self.max_recent = 10  # 最多保存10个最近项目

    def _load_recent_projects(self):
        """从配置文件加载最近项目列表"""
        config_path = os.path.join(os.path.expanduser("~"), ".rstao_config")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("recent_projects", [])
            except (json.JSONDecodeError, OSError):
                pass  # 配置文件损坏时使用空列表
        return []

    def _save_recent_projects(self):
        """保存最近项目列表到配置文件"""
        config_path = os.path.join(os.path.expanduser("~"), ".rstao_config")
        config = {"recent_projects": self.recent_projects}
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass

    def add_recent_project(self, path):
        """添加项目到最近列表"""
        # 移除已存在的相同路径
        if path in self.recent_projects:
            self.recent_projects.remove(path)
        # 添加到开头
        self.recent_projects.insert(0, path)
        # 限制数量
        if len(self.recent_projects) > self.max_recent:
            self.recent_projects = self.recent_projects[:self.max_recent]
        # 保存
        self._save_recent_projects()

    def new_project(self, name, save_path):
        """创建新项目"""
        self.current_project = {
            "project_name": name,
            "created_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "modified_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "current_tab": "特征检测",
            "feature_tab": {},
            "match_tab": {},
            "vector_tab": {}
        }
        self.project_path = save_path
        self.save_project()
        self.add_recent_project(save_path)
        return True

    def save_project(self, feature_state=None, match_state=None, vector_state=None, current_tab=None):
        """保存项目"""
        if not self.current_project or not self.project_path:
            return False
        
        # 更新修改时间
        self.current_project["modified_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 更新各个标签页状态
        if feature_state:
            self.current_project["feature_tab"] = feature_state
        if match_state:
            self.current_project["match_tab"] = match_state
        if vector_state:
            self.current_project["vector_tab"] = vector_state
        if current_tab:
            self.current_project["current_tab"] = current_tab
        
        # 写入文件
        try:
            with open(self.project_path, "w", encoding="utf-8") as f:
                json.dump(self.current_project, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存项目失败: {e}")
            return False

    def load_project(self, path):
        """加载项目"""
        if not os.path.exists(path):
            return False
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.current_project = json.load(f)
            self.project_path = path
            self.add_recent_project(path)
            return self.current_project
        except Exception as e:
            print(f"加载项目失败: {e}")
            return False

    def close_project(self):
        """关闭当前项目"""
        self.current_project = None
        self.project_path = None