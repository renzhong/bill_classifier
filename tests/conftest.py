import os
import sys

# 业务代码用裸 import（如 `from feishu import ...`），这里把源码目录注入 sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.normpath(os.path.join(_HERE, "..", "bill_classifier"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
