"""
Overlay渲染模块 (Overlay Renderer)

负责透明窗口创建、准星图片绘制、缩放、位置更新。
窗口特性：始终置顶、完全透明、鼠标穿透、不获取焦点。
"""

from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import QPixmap, QPainter, QImage
from PyQt5.QtCore import Qt
from pathlib import Path
from typing import Optional

from core.overlay_base import ClickThroughOverlay


class OverlayWindow(ClickThroughOverlay):
    """Overlay透明窗口 - 用于绘制准星"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # 准星相关
        self._crosshair_pixmap: Optional[QPixmap] = None
        self._crosshair_pixmap_inverted: Optional[QPixmap] = None
        self._invert_colors = False
        self._scale = 100.0
        self._offset_x = 0
        self._offset_y = 0
        self._visible = True

        # 图片缓存：{path: (pixmap, inverted_pixmap)}，避免重复从磁盘加载
        self._pixmap_cache = {}
        self._pixmap_cache_max = 50  # 与 _scaled_cache 一致的上限策略，防止长期运行累积
        self._current_path = ""
        # 缩放缓存：(path, scale, inverted) -> scaled_pixmap，避免paintEvent中重复缩放
        self._scaled_cache = {}
        self._last_scale = 100.0

        # 屏幕信息
        self._screen_width = 0
        self._screen_height = 0

        # 初始化窗口
        self._init_window()



    @property
    def current_path(self) -> str:
        """D5: 公共只读属性，替代外部访问 _current_path 私有成员"""
        return self._current_path

    def _init_window(self):
        """初始化窗口大小和位置"""
        screen = QApplication.primaryScreen()
        if screen:
            geometry = screen.geometry()
            self._screen_width = geometry.width()
            self._screen_height = geometry.height()
            self.setGeometry(geometry)
        else:
            self._screen_width = 1920
            self._screen_height = 1080
            self.setGeometry(0, 0, 1920, 1080)

    def set_crosshair(self, image_path: str):
        """设置准星图片（带缓存，避免重复从磁盘加载）"""
        self._current_path = image_path
        if not image_path:
            self._crosshair_pixmap = None
            self._crosshair_pixmap_inverted = None
            self.update()
            return

        # 命中缓存：直接使用，跳过磁盘加载和反色生成（命中路径只读不清）
        if image_path in self._pixmap_cache:
            self._crosshair_pixmap, self._crosshair_pixmap_inverted = self._pixmap_cache[image_path]
            self.update()
            return

        if not Path(image_path).exists():
            print(f"[Overlay] 准星图片不存在: {image_path}")
            self._crosshair_pixmap = None
            self._crosshair_pixmap_inverted = None
            self.update()
            return

        try:
            self._crosshair_pixmap = QPixmap(image_path)
            if self._crosshair_pixmap.isNull():
                print(f"[Overlay] 准星图片加载失败: {image_path}")
                self._crosshair_pixmap = None
                self._crosshair_pixmap_inverted = None
            else:
                # 预生成反色版本并存入缓存
                self._crosshair_pixmap_inverted = self._create_inverted_pixmap(self._crosshair_pixmap)
                # 上限判断在写入前，保证当前项一定在缓存中（命中路径只读不清）
                if len(self._pixmap_cache) >= self._pixmap_cache_max:
                    self._pixmap_cache.clear()
                self._pixmap_cache[image_path] = (self._crosshair_pixmap, self._crosshair_pixmap_inverted)
            self.update()
        except Exception as e:
            print(f"[Overlay] 加载准星图片异常: {e}")
            self._crosshair_pixmap = None
            self._crosshair_pixmap_inverted = None

    def _create_inverted_pixmap(self, pixmap: QPixmap) -> QPixmap:
        """创建反色版本的 pixmap（只反色 RGB，保留 Alpha 通道）"""
        image = pixmap.toImage()
        # 使用 QImage 内置的反色方法，只反色 RGB 通道
        image.invertPixels(QImage.InvertRgb)
        return QPixmap.fromImage(image)

    def set_invert_colors(self, invert: bool):
        """设置是否反色显示"""
        if self._invert_colors != invert:
            self._invert_colors = invert
            self.update()

    def toggle_invert_colors(self) -> bool:
        """切换反色状态，返回新状态"""
        self.set_invert_colors(not self._invert_colors)
        return self._invert_colors

    @property
    def invert_colors(self) -> bool:
        """当前是否反色"""
        return self._invert_colors

    def set_scale(self, scale_percent: float):
        """设置缩放比例(%)"""
        new_scale = max(1.0, min(1000.0, scale_percent))
        if new_scale != self._scale:
            self._scale = new_scale
            self._scaled_cache.clear()
            self.update()

    def set_offset(self, offset_x: int, offset_y: int):
        """设置偏移量(像素)"""
        self._offset_x = int(offset_x)
        self._offset_y = int(offset_y)
        self.update()

    def set_visible(self, visible: bool):
        """设置Overlay可见性"""
        self._visible = visible
        if visible:
            self.show()
        else:
            self.hide()

    def update_screen_geometry(self):
        """更新屏幕几何信息"""
        screen = QApplication.primaryScreen()
        if screen:
            geometry = screen.geometry()
            self._screen_width = geometry.width()
            self._screen_height = geometry.height()
            self.setGeometry(geometry)
            self.update()

    def paintEvent(self, event):
        """绘制事件"""
        if not self._visible:
            return

        # 根据反色状态选择使用哪个 pixmap
        if self._invert_colors and self._crosshair_pixmap_inverted and not self._crosshair_pixmap_inverted.isNull():
            active_pixmap = self._crosshair_pixmap_inverted
        else:
            active_pixmap = self._crosshair_pixmap

        if not active_pixmap or active_pixmap.isNull():
            return

        painter = QPainter(self)
        # 准星缩放不需要抗锯齿，只保留平滑变换
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # 计算缩放后的尺寸
        scale_factor = self._scale / 100.0
        original_width = active_pixmap.width()
        original_height = active_pixmap.height()
        scaled_width = max(1, int(original_width * scale_factor))
        scaled_height = max(1, int(original_height * scale_factor))

        # 缩放缓存：相同(路径,尺寸,反色)直接复用，避免重复SmoothTransformation
        cache_key = (self._current_path, scaled_width, scaled_height, self._invert_colors)
        scaled_pixmap = self._scaled_cache.get(cache_key)
        if scaled_pixmap is None:
            scaled_pixmap = active_pixmap.scaled(
                scaled_width, scaled_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            # 上限判断在写入前，保证当前项一定在缓存中
            if len(self._scaled_cache) >= 50:
                self._scaled_cache.clear()
            self._scaled_cache[cache_key] = scaled_pixmap

        # 计算屏幕中心位置 + 偏移
        center_x = self._screen_width // 2 + self._offset_x
        center_y = self._screen_height // 2 + self._offset_y

        # 计算绘制位置（使图片中心对准屏幕中心）
        draw_x = center_x - scaled_width // 2
        draw_y = center_y - scaled_height // 2

        painter.drawPixmap(draw_x, draw_y, scaled_pixmap)
        painter.end()

    def resizeEvent(self, event):
        """大小变化事件"""
        super().resizeEvent(event)
        self._screen_width = self.width()
        self._screen_height = self.height()


class OverlayRenderer:
    """Overlay渲染器 - 管理Overlay窗口和渲染"""

    def __init__(self, config_manager, state_machine):
        self.config = config_manager
        self.state = state_machine

        # P0-2: Overlay窗口延迟创建，__init__只保存引用，不创建窗口
        self.overlay = None

        # 连接状态变化信号（细粒度：倍率/弹种变化才更新准星，避免全量刷新）
        self.state.magnification_changed.connect(self._on_state_changed)
        self.state.ammo_type_changed.connect(self._on_state_changed)
        self.state.overlay_settings_changed.connect(self._on_state_changed)
        self.state.overlay_toggled.connect(self._on_overlay_toggled)

    def _ensure_overlay(self):
        """P0-2: 懒加载创建Overlay窗口，创建后同步所有状态"""
        if not self.overlay:
            self.overlay = OverlayWindow()
            self._update_crosshair()
            self._update_scale()
            self._update_offset()
            # BUG-13: 创建后兜底设置全局opacity，再调用_update_effective_overlay覆盖为二选一配置
            self.overlay.setWindowOpacity(self.config.get_overlay_opacity())
            self._update_effective_overlay()
            self.overlay.set_visible(self.state.overlay_visible)
        return self.overlay


    def _on_state_changed(self):
        """状态变化处理：更新准星图片 + 缩放偏移"""
        self._ensure_overlay()
        self._update_crosshair()
        self._update_effective_overlay()

    def _update_effective_overlay(self):
        """根据当前载具/弹种/倍率更新缩放偏移（二选一判断在 config 层）"""
        if not self.overlay:
            return
        vehicle = self.state.current_vehicle
        ammo = self.state.current_ammo_type
        mag_idx = self.state.current_magnification_index
        if not vehicle or not ammo:
            # BUG-13: 无载具时兜底设置全局opacity，不直接return
            self.overlay.setWindowOpacity(self.config.get_overlay_opacity())
            return
        effective = self.config.get_effective_overlay(vehicle, ammo, mag_idx)
        self.overlay.set_scale(effective["scale"])
        self.overlay.set_offset(effective["offset_x"], effective["offset_y"])
        # FEATURE-4: 透明度设置（overlay_base已重写setWindowOpacity自动恢复穿透）
        opacity = effective.get("opacity", 1.0)
        self.overlay.setWindowOpacity(max(0.1, min(1.0, opacity)))

    def refresh(self):
        """OPT-4: 公共方法，强制刷新overlay的缩放/偏移/透明度（供外部模块调用，避免访问私有方法）"""
        self._update_effective_overlay()

    def _on_overlay_toggled(self, visible: bool):
        """Overlay显示状态变化"""
        self._ensure_overlay()
        self.overlay.set_visible(visible)

    def _update_crosshair(self):
        """更新准星图片（路径去重：路径不变时跳过，避免载具切换时重复重绘）"""
        if not self.overlay:
            return
        crosshair_path = self.state.get_current_crosshair_path() or ""
        if crosshair_path == self.overlay.current_path:
            return
        self.overlay.set_crosshair(crosshair_path)

    def _update_scale(self):
        """更新缩放比例"""
        if not self.overlay:
            return
        scale = self.config.get_global_scale()
        self.overlay.set_scale(scale)

    def _update_offset(self):
        """更新偏移量"""
        if not self.overlay:
            return
        offset_x = self.config.get_global_offset_x()
        offset_y = self.config.get_global_offset_y()
        self.overlay.set_offset(offset_x, offset_y)

    def update_scale(self, scale: float):
        """更新全局缩放"""
        self.config.set_global_scale(scale)
        self._ensure_overlay()
        self.overlay.set_scale(scale)

    def update_offset(self, offset_x: int, offset_y: int):
        """更新全局偏移（合并写盘，避免两次IO）"""
        self.config.set_global_offset(offset_x, offset_y)
        self._ensure_overlay()
        self.overlay.set_offset(offset_x, offset_y)

    def show(self):
        """显示Overlay"""
        self.state.set_overlay_visible(True)

    def hide(self):
        """隐藏Overlay"""
        self.state.set_overlay_visible(False)

    def toggle(self):
        """切换Overlay显示/隐藏"""
        self.state.toggle_overlay()

    def refresh(self):
        """强制刷新Overlay"""
        self._ensure_overlay()
        self._update_crosshair()
        self._update_scale()
        self._update_offset()
        self.overlay.update()

    def toggle_invert_colors(self) -> bool:
        """切换准星反色，返回新状态"""
        self._ensure_overlay()
        return self.overlay.toggle_invert_colors()

    def set_invert_colors(self, invert: bool):
        """设置准星反色"""
        self._ensure_overlay()
        self.overlay.set_invert_colors(invert)

    @property
    def invert_colors(self) -> bool:
        """当前是否反色"""
        self._ensure_overlay()
        return self.overlay.invert_colors

    def update_screen_geometry(self):
        """更新屏幕几何信息"""
        self._ensure_overlay()
        self.overlay.update_screen_geometry()

    def get_overlay_widget(self) -> QWidget:
        """获取Overlay窗口部件"""
        return self._ensure_overlay()
