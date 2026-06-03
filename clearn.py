# 清理旧授权文件工具
import os

AUTH_PATHS = [
    os.path.join(os.path.expanduser("~"), ".gis_auth"),
    os.path.join(os.environ.get("APPDATA", ""), ".gis_secure"),
    os.path.join(os.path.expanduser("~"), "AppData", "Local", ".gis_license"),
]

for path in AUTH_PATHS:
    if os.path.exists(path):
        try:
            os.remove(path)
            print(f"✅ 已删除：{path}")
        except Exception as e:
            print(f"❌ 删除失败：{path}，原因：{e}")
