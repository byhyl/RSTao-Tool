"""RSTao-Tool 程序入口 — 授权校验 + 启动主程序或激活界面"""

import sys
from tkinter import messagebox

from activation_ui import ActivationUI
from auth import AuthManager
from common.logger import logger
from ui import MainWindow


def start_main():
    """启动主程序"""
    try:
        app = MainWindow()
        app.mainloop()
    except Exception as e:
        logger.critical("主程序启动失败", exc_info=True)
        messagebox.showerror("致命错误", f"主程序启动失败：{str(e)}")
        sys.exit(1)


def main():
    """程序入口"""
    try:
        auth_manager = AuthManager()
        ok, msg = auth_manager.check_auth()

        if ok:
            logger.info("授权校验通过，启动主程序")
            start_main()
        else:
            # 未授权时优先提供试用入口
            trial_ok, trial_msg, trial_days = auth_manager.check_trial()
            if trial_ok and auth_manager.has_trial_available():
                from tkinter import messagebox as mb

                use_trial = mb.askyesno(
                    "试用模式",
                    f"未检测到有效授权。\n\n您有 {trial_days} 天免费试用期。\n是否开始试用？",
                )
                if use_trial:
                    auth_manager.start_trial(trial_days)
                    logger.info("试用模式已启动，启动主程序")
                    start_main()
                    return
            elif trial_ok:
                logger.info(f"试用模式进行中：剩余 {trial_days} 天")
                start_main()
                return

            logger.info(f"授权校验未通过：{msg}，打开激活界面")
            activation_ui = ActivationUI(auth_manager, on_activated=start_main)
            activation_ui.run()
    except Exception as e:
        logger.critical("程序初始化失败", exc_info=True)
        messagebox.showerror("致命错误", f"程序初始化失败：{str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
