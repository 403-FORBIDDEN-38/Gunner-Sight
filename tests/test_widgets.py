"""回归：`gui/widgets.py` 里两个 SSOT 组合控件的**契约**。

它们存在的意义就是"同一交互只有一个实现、使用方零配置"，所以这里锁的是：
- `LinkedSpinSlider`：内部镜像同步**绝不外发信号**（防回路），使用方不用写 blockSignals；
  `set_silent()` 在异常后也必须恢复信号（一行流 idiom 会让控件永久静默且不留痕迹）
- `FilterListPanel`：标签下拉同步要保住当前选中，且无变化时不重建（否则递归刷新）
- 列表在搜索/筛选下恢复选中必须用**实际插入的行号**（曾经的错位 bug）
"""
from PyQt5.QtCore import Qt

from gui.widgets import FilterListPanel, LinkedSpinSlider, set_silent


def _spy(ctl):
    """记录 value_changed 的每次取值"""
    seen = []
    ctl.value_changed.connect(seen.append)
    return seen


def test_linked_spin_slider_mirrors_both_directions(qapp):
    """两个方向都要同步，且**一次用户改动只发一次信号**（内部镜像不得再触发）。"""
    ctl = LinkedSpinSlider((1, 100), initial=50)
    seen = _spy(ctl)
    assert ctl.slider.value() == 50 and ctl.spin.value() == 50

    ctl.spin.setValue(70)                      # 输入框 → 滑块
    assert ctl.slider.value() == 70
    assert seen == [70]

    ctl.slider.setValue(20)                    # 滑块 → 输入框
    assert ctl.spin.value() == 20
    assert seen == [70, 20]


def test_set_value_silent_emits_nothing(qapp):
    """载入配置不得触发 value_changed（否则会回写配置 / 重算预览）。"""
    ctl = LinkedSpinSlider((1, 100))
    seen = _spy(ctl)
    ctl.set_value_silent(88)
    assert seen == []
    assert (ctl.spin.value(), ctl.slider.value()) == (88, 88)


def test_set_silent_restores_signals_after_error(qapp):
    """一行流 idiom 的隐患：中途抛异常会让控件永久静默。`set_silent` 用 finally 兜住。"""
    ctl = LinkedSpinSlider((1, 100))
    try:
        set_silent(ctl.spin, "not-a-number")
    except TypeError:
        pass
    assert ctl.spin.signalsBlocked() is False, "异常后信号必须已恢复"

    seen = _spy(ctl)
    ctl.spin.setValue(30)
    assert seen == [30], "信号恢复后仍能正常联动"


def test_step_value_clamps_within_range(qapp):
    """+/- 按钮走正常信号链，越界由 spin 范围收敛（使用方不再硬编码 max/min）。"""
    ctl = LinkedSpinSlider((10, 100), initial=12)
    seen = _spy(ctl)
    ctl.step_value(-5)
    assert ctl.value() == 10 and ctl.slider.value() == 10
    ctl.step_value(5)
    assert ctl.value() == 15 and seen == [10, 15]


def test_tag_options_keeps_selection_and_falls_back(qapp):
    """标签下拉同步：保住当前选中；选项没变就不重建；选中项消失则回到"全部标签"。"""
    panel = FilterListPanel()
    panel.set_tag_options(["b", "a"])
    assert [panel.tag_filter.itemData(i) for i in range(panel.tag_filter.count())] == [None, "b", "a"]

    panel.tag_filter.setCurrentIndex(1)          # 选中 "b"
    panel.set_tag_options(["b", "a"])            # 无变化：不重建
    assert panel.tag_filter.currentData() == "b"

    panel.set_tag_options(["a", "b", "c"])       # 有变化：重建后仍保持选中
    assert panel.tag_filter.currentData() == "b"

    panel.set_tag_options(["c"])                 # 原选中项没了 → 回落到第一项
    assert panel.tag_filter.currentData() is None and panel.tag_filter.currentIndex() == 0

    panel.search.setText("AbC")
    assert panel.filter_values() == ("abc", None), "搜索词统一小写，使用方无需再 lower()"


def test_list_row_restored_under_filter(config, window):
    """过滤后只剩一项时，选中必须落在它身上。

    旧实现用"源列表下标"（`enumerate` 的 i）恢复选中，过滤后行号与源下标错位：
    例如 [Alpha, Bravo, Charlie] 只筛出 Charlie 时 `setCurrentRow(2)` 越界并**清空**选中，
    表现为"列表有内容但没有选中项 / 参数区不刷新"。
    """
    for name in ("Alpha", "Bravo", "Charlie"):
        config.add_magnifier_preset(name)

    window._create_ui_frame()
    window._create_first_tab()
    window._ensure_tab(window.TAB_MAGNIFIER)
    tab = window.get_tab(window.TAB_MAGNIFIER)

    tab.preset_search.setText("charlie")
    names = [tab.preset_list.item(i).data(Qt.UserRole) for i in range(tab.preset_list.count())]
    assert names == ["Charlie"], "搜索应只留下 Charlie"

    current = tab.preset_list.currentItem()
    assert current is not None, "过滤后必须仍有选中项"
    assert current.data(Qt.UserRole) == "Charlie", "选中的必须是过滤后剩下的那一项"
