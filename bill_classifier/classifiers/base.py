import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from bill_config import BillConfig
from bill_item import BillItem
from category import CategoryInfo

logger = logging.getLogger(__name__)


class CategoryInfoLoader:
    """懒加载飞书分类配置。

    第一次 get() 时才发起 IO；失败/成功结果都缓存，避免依赖它的多个 step
    重复请求。失败时返回 (False, None)，由调用方决定是否跳过自身策略。
    """

    def __init__(self, fetch: Callable[[], "tuple[bool, Optional[CategoryInfo]]"]):
        self._fetch = fetch
        self._loaded = False
        self._ok = False
        self._info: Optional[CategoryInfo] = None

    def get(self) -> "tuple[bool, Optional[CategoryInfo]]":
        if not self._loaded:
            self._loaded = True
            try:
                self._ok, self._info = self._fetch()
            except Exception:
                logger.exception("CategoryInfoLoader fetch 抛异常")
                self._ok = False
                self._info = None
        return self._ok, self._info


@dataclass
class Context:
    """单次 pipeline 运行共享的上下文。

    bill_config:        全量配置
    category_info_loader: 懒加载的飞书分类配置
    gpt_classifier_factory: 工厂函数，调用一次得到一个 GPTClassifier 实例
                            （延迟到真正需要 GPT 的 step 才构造，便于测试时注入 fake）
    """

    bill_config: BillConfig
    category_info_loader: CategoryInfoLoader
    gpt_classifier_factory: Callable[[], object] = field(default=lambda: None)


class Step(ABC):
    name: str = ""

    @abstractmethod
    def run(self, items: List[BillItem], ctx: Context) -> List[BillItem]:
        """对 items 做一次变换，返回新的 list（可与原 list 同对象）。"""
        ...
