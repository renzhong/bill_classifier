from category import ClassifyAlg, ExpenseCategory, Lifecycle
from classifiers.neighbor_inference import NeighborInference

from helpers import make_context, make_item


T0 = 12 * 3600  # 任意基准


def _meituan_unknown(t=T0, payee="美团", item_name="美团订单-25102911100400001305"):
    """构造一条 UNKNOWN 美团 item。"""
    return make_item(
        item_name=item_name, payee=payee, bill_time=t,
        order_id="wechat_meituan_xxx",
    )


def _match_anchor(t, category=ExpenseCategory.CATERING, payee="某餐厅", order_id="anchor_oid_1"):
    """构造一条 MATCH 类锚点（已 CLASSIFIED）。"""
    a = make_item(payee=payee, item_name="餐厅消费", bill_time=t, order_id=order_id)
    a.category = category
    a.classify_alg = ClassifyAlg.MATCH
    a.lifecycle = Lifecycle.CLASSIFIED
    return a


def test_single_meituan_then_match_anchor_forms_group():
    target = _meituan_unknown()
    anchor = _match_anchor(T0 + 180)
    NeighborInference().run([target, anchor], make_context())

    # neighbor_inference 只是标记，不推进 lifecycle
    assert target.lifecycle == Lifecycle.UNPROCESSED
    assert target.category == ExpenseCategory.CATERING
    assert target.classify_alg == ClassifyAlg.FOLLOW
    expected = f"nbr:{anchor.order_id}"
    assert target.group_id == expected
    assert anchor.group_id == expected
    # 锚点本身的 classify_alg 仍保留 MATCH
    assert anchor.classify_alg == ClassifyAlg.MATCH


def test_two_meituan_chain_then_anchor():
    """M, M, A —— 链扩展，组成 3 元组。"""
    m0 = _meituan_unknown(t=T0)
    m1 = _meituan_unknown(t=T0 + 60)
    anchor = _match_anchor(T0 + 200)
    NeighborInference().run([m0, m1, anchor], make_context())

    expected = f"nbr:{anchor.order_id}"
    assert m0.classify_alg == ClassifyAlg.FOLLOW
    assert m1.classify_alg == ClassifyAlg.FOLLOW
    assert m0.group_id == expected
    assert m1.group_id == expected
    assert anchor.group_id == expected


def test_chain_extends_beyond_initial_window_via_meituan_hops():
    """A 在 M0 原始 5min 之外，但通过 M1 的窗口可达。"""
    m0 = _meituan_unknown(t=T0)
    m1 = _meituan_unknown(t=T0 + 200)            # 在 M0 窗口内
    anchor = _match_anchor(T0 + 400)             # 在 M1 窗口内（200+300），超 M0 窗口
    NeighborInference().run([m0, m1, anchor], make_context())

    assert m0.classify_alg == ClassifyAlg.FOLLOW
    assert m1.classify_alg == ClassifyAlg.FOLLOW
    assert anchor.classify_alg == ClassifyAlg.MATCH


def test_meituan_platform_payee_also_triggers():
    target = _meituan_unknown(payee="美团平台商户")
    anchor = _match_anchor(T0 + 60)
    NeighborInference().run([target, anchor], make_context())
    assert target.classify_alg == ClassifyAlg.FOLLOW


def test_no_anchor_in_window_keeps_unknown():
    target = _meituan_unknown()
    far_anchor = _match_anchor(T0 + 301)  # 超 5min
    NeighborInference().run([target, far_anchor], make_context())
    assert target.lifecycle == Lifecycle.UNPROCESSED
    assert target.classify_alg is None


def test_any_classify_alg_anchor_accepted():
    """锚点不限定 classify_alg：MATCH / REGULAR / WET_MARKET 等都可作锚点。"""
    for alg in [ClassifyAlg.REGULAR, ClassifyAlg.WET_MARKET]:
        target = _meituan_unknown()
        anchor = _match_anchor(T0 + 100, category=ExpenseCategory.CATERING)
        anchor.classify_alg = alg
        NeighborInference().run([target, anchor], make_context())
        assert target.classify_alg == ClassifyAlg.FOLLOW, f"alg={alg} 应触发"
        assert target.category == ExpenseCategory.CATERING


def test_anchor_in_past_does_not_count_one_directional():
    """单向：锚点在 target 之前不应触发。"""
    early_anchor = _match_anchor(T0 - 60)
    target = _meituan_unknown(t=T0)
    NeighborInference().run([early_anchor, target], make_context())
    assert target.lifecycle == Lifecycle.UNPROCESSED


def test_anchor_at_window_boundary_inclusive():
    """5min = 边界包含；超 1 秒不算。"""
    target = _meituan_unknown()
    boundary = _match_anchor(T0 + 300)
    NeighborInference().run([target, boundary], make_context())
    assert target.category == ExpenseCategory.CATERING

    target2 = _meituan_unknown(t=2 * T0)
    over = _match_anchor(2 * T0 + 301)
    NeighborInference().run([target2, over], make_context())
    assert target2.lifecycle == Lifecycle.UNPROCESSED


def test_non_meituan_payee_not_trigger():
    """非美团 payee 不触发链。"""
    target = make_item(payee="星巴克", item_name="拿铁", bill_time=T0)
    anchor = _match_anchor(T0 + 60)
    NeighborInference().run([target, anchor], make_context())
    assert target.lifecycle == Lifecycle.UNPROCESSED
    assert target.group_id is None


def test_dianping_jd_no_longer_trigger():
    """新算法下，大众点评 / 京东等不再当触发账单。"""
    for payee in ["大众点评", "京东", "京东商家"]:
        target = make_item(payee=payee, item_name="某订单", bill_time=T0)
        anchor = _match_anchor(T0 + 60)
        NeighborInference().run([target, anchor], make_context())
        assert target.lifecycle == Lifecycle.UNPROCESSED, f"payee={payee} 不应触发"


def test_already_classified_meituan_skipped():
    """已分类的美团 item 不被覆盖。"""
    target = _meituan_unknown()
    target.category = ExpenseCategory.CATERING
    target.lifecycle = Lifecycle.CLASSIFIED
    anchor = _match_anchor(T0 + 60, category=ExpenseCategory.MEDICAL)
    NeighborInference().run([target, anchor], make_context())
    assert target.category == ExpenseCategory.CATERING
    assert target.group_id is None


def test_anchor_without_order_id_uses_timestamp_group():
    """锚点没 order_id 时 group_id 用时间戳。"""
    target = _meituan_unknown()
    anchor = _match_anchor(T0 + 60, order_id="")
    NeighborInference().run([target, anchor], make_context())
    expected = f"nbr:t{int(anchor.bill_time)}"
    assert target.group_id == expected
    assert anchor.group_id == expected


def test_multiple_independent_meituan_groups():
    """两组互不相邻的 meituan 各自独立配对。"""
    t1, t2 = T0, T0 + 1800
    m_a = _meituan_unknown(t=t1)
    a_a = _match_anchor(t1 + 100, category=ExpenseCategory.CATERING, order_id="o1")
    m_b = _meituan_unknown(t=t2)
    a_b = _match_anchor(t2 + 100, category=ExpenseCategory.MEDICAL, order_id="o2")
    NeighborInference().run([m_a, a_a, m_b, a_b], make_context())
    assert m_a.category == ExpenseCategory.CATERING
    assert m_a.group_id == "nbr:o1"
    assert m_b.category == ExpenseCategory.MEDICAL
    assert m_b.group_id == "nbr:o2"


def test_empty_or_single_item_list():
    NeighborInference().run([], make_context())
    one = _meituan_unknown()
    NeighborInference().run([one], make_context())
    assert one.lifecycle == Lifecycle.UNPROCESSED
