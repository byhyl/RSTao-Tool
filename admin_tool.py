"""RSTao-Tool 授权管理中心 — 启动入口"""

import sys
from pathlib import Path
from tkinter import messagebox

# Ensure the root is on path
sys.path.insert(0, str(Path(__file__).parent))

from admin_tool.app import AdminTool

if __name__ == "__main__":
    try:
        app = AdminTool()
        app.run()
    except Exception as e:
        messagebox.showerror("致命错误", f"启动失败: {e}")
        sys.exit(1)
