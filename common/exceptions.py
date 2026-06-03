class AppBaseException(Exception):
    """应用程序基异常"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# 文件操作异常
class FileReadError(AppBaseException):
    pass


class FileWriteError(AppBaseException):
    pass


class FileFormatError(AppBaseException):
    pass


# 算法异常
class AlgorithmError(AppBaseException):
    pass


class ParameterError(AppBaseException):
    pass


# UI异常
class UIError(AppBaseException):
    pass
