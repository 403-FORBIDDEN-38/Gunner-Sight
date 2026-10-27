"""放大镜模块：屏幕中心圆形放大 overlay

三概念分离：
- 电闸（config.magnifier.enabled）：模块是否加载，决定overlay创建/销毁
- 开关（toggle热键）：功能+窗口同时开关
- 暂离（suspend）：只控制窗口可视性，不影响开关状态

倍率与半径各有两个数，不是一个：
- 旋钮 `_zoom` / `_radius`：持久化到 config，决定**松开屏息后**落在哪
- 屏息加成 `_breath_zoom` / `_breath_radius`：只在按住期间存在，松开即清零

屏幕上看到的是两者之和（`_effective_*`）。加成不是"第二份倍率"，它是
"这次按住加了 +N、松开要减回 -N"的在途记账——所以按住屏息期间调旋钮，
松开时只撤掉加成，调过的值留着。

截屏+缩放跑在副线程，主线程只负责paint。
"""
import threading
import time
import mss
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QRect, QThread, pyqtSignal, pyqtSlot
from core.logger import logger
from core.win32_utils import WDA_EXCLUDEFROMCAPTURE, user32
from PyQt5.QtGui import QPainter, QColor, QPen, QRegion, QImage, QPixmap

ZOOM_MIN = 1.0
RADIUS_MIN = 10


class _GrabWorker(QThread):
    """副线程：循环 grab + scale，发新帧信号"""
    frame_ready = pyqtSignal(QImage)
    error = pyqtSignal(str)  # 抓屏线程异常退出（不静默）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._cam = None
        self._lock = threading.Lock()
        self._region = None
        self._src_size = 2
        self._dst_w = 400
        self._dst_h = 400
        self._interval = 16
        self._running = True

    def configure(self, region, src_size, dst_w, dst_h, interval):
        with self._lock:
            self._region = region
            self._src_size = src_size
            self._dst_w = dst_w
            self._dst_h = dst_h
            self._interval = interval
        self._active = True

    def run(self):
        # 整体 try/finally：任何异常路径都保证 mss 句柄释放（泄漏会累积 GDI 资源），
        # 异常经 error 信号报出而不是静默死亡（调用方只会看到画面不再刷新）。
        try:
            self._grab_loop()
        except Exception as e:
            logger.exception("[GrabWorker] 抓屏线程异常")
            self.error.emit(str(e))
        finally:
            cam, self._cam = self._cam, None
            if cam is not None:
                try:
                    cam.close()
                except Exception:
                    pass

    def _grab_loop(self):
        # 去掉CAPTUREBLT：Squad不是layered window，纯SRCCOPY快20-40%
        import mss.windows.gdi as _gdi
        _gdi.CAPTUREBLT = 0
        self._cam = mss.MSS()
        while self._running:
            if not self._active:
                self.msleep(50)
                continue
            t0 = time.perf_counter()
            with self._lock:
                region = self._region
                src_size = self._src_size
                dst_w = self._dst_w
                dst_h = self._dst_h
                interval = self._interval
            # region is (left, top, right, bottom)
            monitor = {"left": region[0], "top": region[1],
                       "width": src_size, "height": src_size}
            frame = self._cam.grab(monitor)
            if frame is not None:
                # .raw直接引用内部buffer，比.bgra少一层拷贝
                src = QImage(frame.raw, src_size, src_size, QImage.Format_RGB32)
                if src_size == dst_w:
                    out = src.copy()
                else:
                    out = src.scaled(dst_w, dst_h,
                                     Qt.IgnoreAspectRatio, Qt.FastTransformation)
                self.frame_ready.emit(out)
            elapsed = (time.perf_counter() - t0) * 1000
            sleep_ms = max(0, interval - elapsed)
            self.msleep(int(sleep_ms))

    def stop(self):
        self._running = False
        if not self.wait(2000):
            logger.warning(
                "[GrabWorker] 线程未在 2s 内退出，mss 句柄可能未释放"
            )


class MagnifierOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._radius = 200          # 旋钮：松开屏息后的半径
        self._zoom = 2.0            # 旋钮：松开屏息后的倍率
        self._breath_radius = 0     # 屏息加成（在途，松开即清零）
        self._breath_zoom = 0.0
        self._hold_active = False
        self._active = False
        self._suspended = False
        self._scaled = None
        self._pixmap = None
        self._fps = 60
        self._worker = None
        self._ox = 0
        self._oy = 0

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._resize_circle()

    # ===== 派生值：屏幕上实际生效的大小与倍率 =====
    def _effective_radius(self) -> int:
        return max(RADIUS_MIN, self._radius + self._breath_radius)

    def _effective_zoom(self) -> float:
        return max(ZOOM_MIN, self._zoom + self._breath_zoom)

    def _resize_circle(self):
        size = self._effective_radius() * 2
        self.resize(size, size)
        self.setMask(QRegion(QRect(0, 0, size, size), QRegion.Ellipse))

    def set_radius(self, r: int):
        """设旋钮半径（松开屏息后的大小）。屏息加成不受影响。"""
        self._radius = max(RADIUS_MIN, int(r))
        self._resize_circle()
        self._reposition()
        self._reconfigure_worker()
        if self._active and not self._suspended and self._effective_zoom() > ZOOM_MIN:
            self.show()

    def set_zoom(self, z: float):
        """设旋钮倍率。屏息加成不受影响：按住期间看到的是 旋钮+加成。"""
        self._zoom = max(ZOOM_MIN, float(z))
        self._apply_visibility()
        self._reconfigure_worker()

    def adjust_zoom(self, delta: float) -> float:
        """按步长调旋钮；旋钮顶到下限时，差额转记到屏息加成上。

        返回新的旋钮值（调用方据此持久化）。若到限就什么都不做，热键会变成
        "按了没反应"，违反手感；把差额记在屏息账上至少画面会动，而松开屏息
        仍然落回旋钮——不会把临时效果写成持久值。
        """
        old = self._zoom
        self._zoom = max(ZOOM_MIN, old + delta)
        spill = delta - (self._zoom - old)      # 旋钮没吃下的那部分
        if self._hold_active and spill:
            self._breath_zoom = max(0.0, self._breath_zoom + spill)
        self._apply_visibility()
        self._reconfigure_worker()
        return self._zoom

    def zoom(self) -> float:
        """屏幕上当前的倍率（旋钮 + 屏息加成）。"""
        return self._effective_zoom()

    def radius(self) -> int:
        """屏幕上当前的半径（旋钮 + 屏息加成）。"""
        return self._effective_radius()

    def set_fps(self, fps: int):
        self._fps = max(15, min(144, fps))
        self._reconfigure_worker()

    def toggle_breath_hold(self, step: int = 20, zoom_step: float = 0.0):
        """屏息：按住时加一份临时半径/倍率，松开时把**同一份**减回去。

        加的是偏移不是快照——按住期间改旋钮（set_zoom/set_radius/adjust_zoom），
        松开只撤加成，改过的值留着。热键 toggle 模式下同一函数连按两次即一开一合。
        """
        if not self._hold_active:
            self._hold_active = True
            self._breath_radius = max(0, int(step))
            self._breath_zoom = max(0.0, float(zoom_step))
        else:
            self._hold_active = False
            self._breath_radius = 0
            self._breath_zoom = 0.0
        self._resize_circle()
        self._reposition()
        self._reconfigure_worker()
        self._apply_visibility()

    # ===== 开关（功能+窗口）=====
    def set_active(self, active: bool):
        self._active = active
        self._apply_visibility()

    def is_active(self) -> bool:
        return self._active

    # ===== 暂离（只控制可视性）=====
    def set_suspended(self, suspended: bool):
        self._suspended = suspended
        self._apply_visibility()

    def _apply_visibility(self):
        # 1x倍率不需要放大，直接停截隐藏；暂离也停截
        zoom = self._effective_zoom()
        should_show = self._active and not self._suspended and zoom > ZOOM_MIN
        if should_show:
            self._reposition()
            self.show()
            user32.SetWindowDisplayAffinity(
                int(self.winId()), WDA_EXCLUDEFROMCAPTURE
            )
        else:
            self.hide()
        # 1x或暂离时停止抓屏
        need_worker = self._active and not self._suspended and zoom > ZOOM_MIN
        if need_worker and not (self._worker and self._worker.isRunning()):
            self._start_worker()
        elif not need_worker and self._worker:
            self._stop_worker()

    def set_offset(self, ox: int, oy: int):
        self._ox = int(ox)
        self._oy = int(oy)
        self._reposition()

    def _reposition(self):
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        self.move((sw - self.width()) // 2 + self._ox, (sh - self.height()) // 2 + self._oy)

    def _compute_region(self):
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        cx, cy = sw // 2, sh // 2
        src_size = max(2, int(self._effective_radius() * 2 / self._effective_zoom()))
        left = cx - src_size // 2
        top = cy - src_size // 2
        return (left, top, left + src_size, top + src_size), src_size

    def _start_worker(self):
        self._stop_worker()
        self._worker = _GrabWorker(self)
        region, src_size = self._compute_region()
        interval = int(1000 / self._fps)
        self._worker.configure(region, src_size, self.width(), self.height(), interval)
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _stop_worker(self):
        if self._worker:
            self._worker.stop()
            self._worker = None

    def _on_worker_error(self, msg: str):
        """抓屏线程异常退出（不静默）：日志留痕，用户可重新开关放大镜。"""
        logger.warning(f"[放大镜] 抓屏线程异常退出: {msg}")

    def closeEvent(self, event):
        self._stop_worker()
        super().closeEvent(event)

    def _reconfigure_worker(self):
        if self._worker and self._worker.isRunning():
            region, src_size = self._compute_region()
            interval = int(1000 / self._fps)
            self._worker.configure(region, src_size, self.width(), self.height(), interval)

    @pyqtSlot(QImage)
    def _on_frame(self, img):
        # 尺寸不变就复用QPixmap，避免每帧重新上传GPU
        if self._pixmap is None or self._pixmap.size() != img.size():
            self._pixmap = QPixmap.fromImage(img)
        else:
            p = QPainter(self._pixmap)
            p.drawImage(0, 0, img)
            p.end()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._pixmap:
            if self._pixmap.size() == self.size():
                painter.drawPixmap(0, 0, self._pixmap)
            else:
                painter.drawPixmap(0, 0, self.width(), self.height(), self._pixmap)
        pen = QPen(QColor(0, 0, 0, 200))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(1, 1, self.width() - 2, self.height() - 2)
        painter.end()
