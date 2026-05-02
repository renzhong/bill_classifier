from bill_item import ClassifyAlg
from category import ExpenseCategory
from classifiers.neighbor_inference import NeighborInference

from helpers import make_context, make_item


T0 = 12 * 3600  # 任意基准


def _meituan_unknown(t=T0, item_name="美团订单-25102911100400001305", payee="美团"):
    """构造一条低信息量 UNKNOWN 美团 item。"""
    return make_item(
        item_name=item_name, payee=payee, bill_time=t,
        order_id="wechat_meituan_xxx",
    )


def _match_anchor(t, category=ExpenseCategory.CATERING, payee="某餐厅", order_id="anchor_oid_1"):
    """构造一条 MATCH 类锚点。"""
    a = make_item(payee=payee, item_name="餐厅消费", bill_time=t, order_id=order_id)
    a.category = category
    a.classify_alg = ClassifyAlg.MATCH
    return a


def test_unique_match_anchor_within_window_marks_neighbor():
    target = _meituan_unknown()
    anchor = _match_anchor(T0 + 180)  # 3 分钟后
    NeighborInference().run([target, anchor], make_context())

    assert target.category == ExpenseCategory.CATERING
    assert target.classify_alg == ClassifyAlg.NEIGHBOR
    # 共享 neighbor_group：基于锚点的 order_id
    assert target.neighbor_group == f"nbr:{anchor.order_id}"
    assert anchor.neighbor_group == f"nbr:{anchor.order_id}"
    # 锚点本身的 classify_alg 仍保留 MATCH（信息不丢失）
    assert anchor.classify_alg == ClassifyAlg.MATCH


def test_no_match_anchor_in_window_keeps_unknown():
    target = _meituan_unknown()
    far_anchor = _match_anchor(T0 + 301)  # 超出 5 分钟
    NeighborInference().run([target, far_anchor], make_context())
    assert target.category == ExpenseCategory.UNKNOWN
    assert target.classify_alg == ClassifyAlg.UNKNOWN
    assert target.neighbor_group is None


def test_two_match_anchors_in_window_keeps_unknown():
    target = _meituan_unknown()
    a1 = _match_anchor(T0 + 60, category=ExpenseCategory.CATERING)
    a2 = _match_anchor(T0 + 200, category=ExpenseCategory.DAILY_EXPENSES)
    NeighborInference().run([target, a1, a2], make_context())
    assert target.category == ExpenseCategory.UNKNOWN
    assert target.classify_alg == ClassifyAlg.UNKNOWN


def test_anchor_in_past_does_not_count_one_directional():
    """单向：锚点在 target 之前，不应触发命中。"""
    early_anchor = _match_anchor(T0 - 60)
    target = _meituan_unknown(t=T0)
    NeighborInference().run([early_anchor, target], make_context())
    assert target.category == ExpenseCategory.UNKNOWN


def test_anchor_at_window_boundary_inclusive():
    """窗口边界 = 5 分钟整恰好包含；恰好越过则不算。"""
    target = _meituan_unknown()
    # 边界值刚好等于 window：window_seconds=300，差 300 秒应包含
    boundary = _match_anchor(T0 + 300)
    NeighborInference().run([target, boundary], make_context())
    assert target.category == ExpenseCategory.CATERING

    # 恰好越过 1 秒
    target2 = _meituan_unknown(t=2 * T0)
    over = _match_anchor(2 * T0 + 301)
    NeighborInference().run([target2, over], make_context())
    assert target2.category == ExpenseCategory.UNKNOWN


def test_non_match_anchors_ignored():
    """REGULAR / HISTORY / WET_MARKET / NEIGHBOR / GPT 都不是合格锚点。"""
    for alg in [ClassifyAlg.REGULAR, ClassifyAlg.HISTORY, ClassifyAlg.WET_MARKET,
                ClassifyAlg.NEIGHBOR, ClassifyAlg.GPT]:
        target = _meituan_unknown()
        anchor = _match_anchor(T0 + 100)
        anchor.classify_alg = alg  # 改成非 MATCH 锚点
        NeighborInference().run([target, anchor], make_context())
        assert target.category == ExpenseCategory.UNKNOWN, f"alg={alg} 不应触发"


def test_non_low_info_payee_skipped():
    """普通 payee 即使在窗口内有锚点也不触发本 step。"""
    target = make_item(payee="星巴克", item_name="拿铁", bill_time=T0)
    anchor = _match_anchor(T0 + 60)
    NeighborInference().run([target, anchor], make_context())
    assert target.category == ExpenseCategory.UNKNOWN
    assert target.neighbor_group is None


def test_already_classified_skipped():
    """已分类的 item 即使是低信息量 payee 也不被覆盖。"""
    target = _meituan_unknown()
    target.category = ExpenseCategory.CATERING  # 假设之前 step 已分
    anchor = _match_anchor(T0 + 60, category=ExpenseCategory.MEDICAL)
    NeighborInference().run([target, anchor], make_context())
    # 不被覆盖
    assert target.category == ExpenseCategory.CATERING
    # 也不打 neighbor_group
    assert target.neighbor_group is None


def test_dianping_payee_triggers():
    target = make_item(payee="大众点评", item_name="某订单号-1234567890", bill_time=T0)
    anchor = _match_anchor(T0 + 120)
    NeighborInference().run([target, anchor], make_context())
    assert target.classify_alg == ClassifyAlg.NEIGHBOR


def test_jd_with_order_id_pattern_triggers():
    """payee=京东 + item_name 含 '订单编号' 触发。"""
    target = make_item(payee="京东", item_name="商品-订单编号:12345", bill_time=T0)
    anchor = _match_anchor(T0 + 90, category=ExpenseCategory.DAILY_EXPENSES)
    NeighborInference().run([target, anchor], make_context())
    assert target.classify_alg == ClassifyAlg.NEIGHBOR
    assert target.category == ExpenseCategory.DAILY_EXPENSES


def test_non_low_info_payee_with_order_id_in_item_name_triggers():
    """payee 不在白名单，但 item_name 含订单号特征也触发。"""
    target = make_item(
        payee="某不知名商家",
        item_name="美团订单-25102911100400001305",
        bill_time=T0,
    )
    anchor = _match_anchor(T0 + 90)
    NeighborInference().run([target, anchor], make_context())
    assert target.classify_alg == ClassifyAlg.NEIGHBOR


def test_anchor_without_order_id_uses_timestamp_group():
    """锚点没有 order_id 时，neighbor_group 用时间戳。"""
    target = _meituan_unknown()
    anchor = _match_anchor(T0 + 60, order_id="")
    NeighborInference().run([target, anchor], make_context())
    expected = f"nbr:t{int(anchor.bill_time)}"
    assert target.neighbor_group == expected
    assert anchor.neighbor_group == expected


def test_multiple_low_info_targets_each_paired_independently():
    """两条独立的 UNKNOWN 美团各自配对独立的锚点。"""
    t1, t2 = T0, T0 + 1800  # 间隔 30 分钟，互不相邻
    target1 = _meituan_unknown(t=t1)
    anchor1 = _match_anchor(t1 + 100, category=ExpenseCategory.CATERING, order_id="o1")
    target2 = _meituan_unknown(t=t2)
    anchor2 = _match_anchor(t2 + 100, category=ExpenseCategory.MEDICAL, order_id="o2")
    NeighborInference().run([target1, anchor1, target2, anchor2], make_context())
    assert target1.category == ExpenseCategory.CATERING
    assert target1.neighbor_group == "nbr:o1"
    assert target2.category == ExpenseCategory.MEDICAL
    assert target2.neighbor_group == "nbr:o2"


def test_empty_or_single_item_list():
    NeighborInference().run([], make_context())
    one = _meituan_unknown()
    NeighborInference().run([one], make_context())
    assert one.category == ExpenseCategory.UNKNOWN
