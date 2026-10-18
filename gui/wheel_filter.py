"""全局滚轮事件过滤器。

无焦点的 QComboBox/QSpinBox/QDoubleSpinBox 不吞滚轮，QSlider 总是拦截滚轮：
- 父链有 QAbstractScrollArea 时，转发滚轮给 viewport（让页面滚动）
- 父链无滚动区时，直接忽略（防误触，等同于原 NoWheelComboBox 行为）

替代 NoWheelComboBox/NoWheelSlider 子类，统一所有原生控件行为。
GS 只有这一处滚轮过滤器；MainWindow 曾经另装一个只处理三种控件的过滤器，
既与这里重复（同名异实现），又因为没反注册而在窗口销毁后留下悬空指针。
"""
from PyQt5.QtCore import QObject, QEvent
from PyQt5.QtWidgets import QAbstractScrollArea, QApplication, QComboBox, QDoubleSpinBox, QSlider, QSpinBox

_INSTANCE = None


def install_no_wheel_filter(app) -> "NoWheelFilter":
    """把全局滚轮过滤器装到 application 上，并**持住引用**。

    PyQt5 的 installEventFilter 不接管过滤器所有权：若传入临时对象
    （`app.installEventFilter(NoWheelFilter())`），语句结束后过滤器就被回收，
    QApplication 上只剩悬空指针——过滤器静默失效（用户以为是"防误触生效"），
    之后投递事件还可能直接崩溃。因此必须保留一个长期引用。
    """
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = NoWheelFilter()
    app.installEventFilter(_INSTANCE)
    return _INSTANCE


class NoWheelFilter(QObject):
    _TARGETS = (QComboBox, QSpinBox, QDoubleSpinBox)
    _SLIDER_TARGETS = (QSlider,)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and isinstance(obj, self._SLIDER_TARGETS):
            # QSlider 滚轮直接改值（无需焦点），总是拦截防误触
            return True
        if event.type() == QEvent.Wheel and isinstance(obj, self._TARGETS):
            if not obj.hasFocus():
                # 向上找最近的滚动区，转发滚轮让页面滚动
                parent = obj.parent()
                while parent is not None:
                    if isinstance(parent, QAbstractScrollArea):
                        QApplication.sendEvent(parent.viewport(), event)
                        return True
                    parent = parent.parent()
                # 无滚动区（如适配页/载具配置页），直接吞掉防误触
                return True
        return super().eventFilter(obj, event)
