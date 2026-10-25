
"""
Overlay渲染模块 (Overlay Renderer)

三层叠加渲染（从下到上）：
  1. vehicle_ui（载具 UI）— 全屏整图，不受 overlay 影响
  2. ammo_ui（弹种 UI）— 全屏整图，不受 overlay 影响
  3. crosshair（弹道图）— 受载具 overlay 的 scale/offset 影响，居中缩放绘制

透明区域裁剪：
  - 所有图片加载时后台扫描非透明区域 bbox，裁剪后存储
  - crosshair 用 QPixmap（GPU 加速缩放），UI 层用 QImage（省显存）
  - 绘制时用 drawPixmap/drawImage(targetRect, image, sourceRect)，Qt 一次性缩放+裁剪
  - 裁剪前后像素级完全一致（已验证差异=0）

缓存：
  _crop_cache: 所有图片的 CropResult（QImage），上限50，LRU
  _crosshair_pixmap_cache: crosshair 的 QPixmap，上限50，LRU
  _inverted_cache: 反色版（crosshair QPixmap / UI QImage），上限15，LRU
"""

from collections import OrderedDict
from pathlib import Path
import tempfile

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication

from core.bbox_crop import BboxCache, BboxScanner, CropResult, load_with_bbox
from core.overlay_base import ClickThroughOverlay


class OverlayWindow(ClickThroughOverlay):
    """Overlay透明窗口 - 三层叠加渲染 + 透明区域裁剪"""

    def __init__(self, parent=None, config_dir=None):
        super().__init__(parent)

        # 当前层
        self._crosshair_path = ""
        self._crosshair_crop = None      # CropResult or None
        self._crosshair_pixmap = None    # QPixmap
        self._vehicle_ui_path = ""
        self._vehicle_ui_crop = None     # CropResult (QImage)
        self._ammo_ui_path = ""
        self._ammo_ui_crop = None        # CropResult (QImage)

        self._invert_colors = False
        self._scale = 100.0
        self._offset_x = 0
        self._offset_y = 0
        self._visible = True

        # 适配参数
        self._resource_w = 2560
        self._resource_h = 1440
        self._screen_width = 1920
        self._screen_height = 1080
        self._display_w = 0
        self._display_h = 0
        self._sx_override = 0.0
        self._sy_override = 0.0
        self._sx_adapt_mode = "expand"
        self._sy_adapt_mode = "expand"
        self._selected_screen_name = ""

        # 缓存
        self._crop_cache = OrderedDict()
        self._crop_cache_max = 50
        self._crosshair_pixmap_cache = OrderedDict()
        self._crosshair_pixmap_cache_max = 50
        self._inverted_cache = OrderedDict()
        self._inverted_cache_max = 15
        self._pending_scans = {}

        # 后台扫描 + bbox 缓存（跟随 ConfigManager 的数据目录决策：
        # 可写时在便携 config/，只读安装降级 %APPDATA%——见 core/config/base.py）
        import sys as _sys
        from pathlib import Path as _Path
        if config_dir is not None:
            bbox_cache_file = _Path(config_dir) / "bbox_cache.json"
        else:
            _base = _Path(_sys.executable).parent if getattr(_sys, 'frozen', False) else _Path(__file__).parent.parent
            bbox_cache_file = _base / "config" / "bbox_cache.json"
        try:
            bbox_cache_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            # 只读位置连缓存目录都建不了：退 %TEMP%（缓存可弃，绝不阻断启动，P4/P5）
            bbox_cache_file = _Path(tempfile.gettempdir()) / "GunnerSight" / "bbox_cache.json"
        self._bbox_cache = BboxCache(bbox_cache_file, resources_dir=self._resources_dir())
        self._scanner = BboxScanner(self._bbox_cache)
        self._scanner.scan_done.connect(self._on_scan_done)
        self._scanner.start()
        # 启动即后台补扫全资源库
        self._prescan_all_resources()

    def closeEvent(self, event):
        # M1：scanner 是常驻线程（队列空时 wait，不自退）。窗口关闭必须显式
        # 请求退出并等它结束——否则窗口销毁后 scan_done 仍 emit 到已删对象。
        scanner = getattr(self, "_scanner", None)
        if scanner is not None:
            scanner.request_stop()
            scanner.wait(2000)
        super().closeEvent(event)

    def _prescan_all_resources(self):
        """后台遍历resources目录，补扫缺失bbox的图片。"""
        try:
            res = self._resources_dir()
            if not res.exists():
                return
            all_paths = []
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                all_paths.extend(str(p) for p in res.rglob(ext))
            if all_paths:
                self.prescan_paths(all_paths)
        except Exception:
            pass

    # ============================================================
    # 层设置
    # ============================================================

    def set_layers(self, crosshair_path="", vehicle_ui="", ammo_ui=""):
        # 路径全没变 → 跳过（P2：相同路径不重新取资源）
        if (crosshair_path == self._crosshair_path
                and vehicle_ui == self._vehicle_ui_path
                and ammo_ui == self._ammo_ui_path):
            return

        # 保存旧路径用于比较
        old_vehicle_ui = self._vehicle_ui_path
        old_ammo_ui = self._ammo_ui_path

        self._crosshair_path = crosshair_path
        self._vehicle_ui_path = vehicle_ui
        self._ammo_ui_path = ammo_ui

        # 加载 crosshair：缓存命中则立即替换，未命中则保持上一张，后台完成后替换
        if crosshair_path:
            self._load_crosshair(crosshair_path)
        else:
            self._crosshair_crop = None
            self._crosshair_pixmap = None

        # 加载 UI 层：未命中时保持上一张，后台完成后替换
        if vehicle_ui != old_vehicle_ui:
            if vehicle_ui:
                crop = self._load_ui_crop(vehicle_ui)
                if crop is not None:
                    self._vehicle_ui_crop = crop
            else:
                self._vehicle_ui_crop = None
        if ammo_ui != old_ammo_ui:
            if ammo_ui:
                crop = self._load_ui_crop(ammo_ui)
                if crop is not None:
                    self._ammo_ui_crop = crop
            else:
                self._ammo_ui_crop = None

        self.update()

    def set_crosshair(self, image_path):
        self.set_layers(crosshair_path=image_path)

    @staticmethod
    def _resources_dir():
        """返回 resources 目录路径（兼容源码和 Nuitka 打包）"""
        import sys
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent / "resources"
        return Path(__file__).resolve().parent.parent / "resources"

    def prescan_paths(self, paths):
        """低优先级预扫描一批路径（插队尾），已缓存的跳过。供切载具时预扫该载具所有图。"""
        to_scan = []
        for p in paths:
            if not p or p in self._pending_scans or p in self._crop_cache:
                continue
            try:
                mtime = Path(p).stat().st_mtime_ns
            except OSError:
                continue
            if not self._bbox_cache.has(p, mtime):
                to_scan.append(p)
        if to_scan:
            self._scanner.submit_many(to_scan)

    # ============================================================
    # 加载逻辑
    # ============================================================

    def _get_crop(self, path):
        """从缓存取 CropResult。bbox_cache 命中则主线程直接加载裁剪（~20ms），否则提交后台扫描返回 None"""
        if not path:
            return None
        # 检查 crop 缓存
        if path in self._crop_cache:
            try:
                current_mtime = Path(path).stat().st_mtime_ns
            except OSError:
                current_mtime = 0
            if self._crop_cache[path][1] == current_mtime:
                self._crop_cache.move_to_end(path)
                return self._crop_cache[path][0]
            else:
                del self._crop_cache[path]
                self._inverted_cache.pop(path, None)
        # bbox 元数据命中：主线程直接加载+裁剪（跳过 250ms 扫描，只需 ~20ms IO+裁剪）
        try:
            current_mtime = Path(path).stat().st_mtime_ns
        except OSError:
            current_mtime = 0
        cached_bbox = self._bbox_cache.get(path, current_mtime)
        if cached_bbox is not None:
            result = load_with_bbox(path, cached_bbox)
            if result is not None:
                if len(self._crop_cache) >= self._crop_cache_max:
                    self._crop_cache.popitem(last=False)
                self._crop_cache[path] = (result, current_mtime)
                return result
        # bbox 未命中：提交后台扫描，返回 None（调用方保持上一张）
        if path not in self._pending_scans:
            tid = self._scanner.submit(path)
            self._pending_scans[path] = tid
        return None

    def _on_scan_done(self, path, result):
        """后台扫描完成回调"""
        self._pending_scans.pop(path, None)
        if result is None:
            return
        # 存入缓存
        try:
            mtime = Path(path).stat().st_mtime_ns
        except OSError:
            mtime = 0
        if len(self._crop_cache) >= self._crop_cache_max:
            self._crop_cache.popitem(last=False)
        self._crop_cache[path] = (result, mtime)
        # M5：仅对当前准星路径构建 pixmap（GPU 上传只属于准星）。UI 层全屏整图
        # （2K 载具/弹种图）只进 crop 缓存，不再塞进 crosshair pixmap 缓存
        # （上限 50，白白 GPU 上传+挤占准星缓存）。非当前路径的准星图下次切回时
        # 走 _load_crosshair 的 miss 分支现建，行为不变。
        if path == self._crosshair_path:
            pixmap = QPixmap.fromImage(result.image)
            if len(self._crosshair_pixmap_cache) >= self._crosshair_pixmap_cache_max:
                self._crosshair_pixmap_cache.popitem(last=False)
            self._crosshair_pixmap_cache[path] = (pixmap, mtime, result.orig_w, result.orig_h, result.bbox_x, result.bbox_y)
        # 如果是当前层，更新并刷新；清除反色缓存避免旧图残留
        if path == self._crosshair_path:
            self._crosshair_crop = result
            self._crosshair_pixmap = pixmap
            self._inverted_cache.pop(path, None)
            self.update()
        elif path == self._vehicle_ui_path:
            self._vehicle_ui_crop = result
            self.update()
        elif path == self._ammo_ui_path:
            self._ammo_ui_crop = result
            self.update()

    def _load_crosshair(self, path):
        """加载 crosshair：优先用裁剪后的 QPixmap，fallback 用原图"""
        # 检查 pixmap 缓存
        if path in self._crosshair_pixmap_cache:
            try:
                current_mtime = Path(path).stat().st_mtime_ns
            except OSError:
                current_mtime = 0
            entry = self._crosshair_pixmap_cache[path]
            if entry[1] == current_mtime:
                self._crosshair_pixmap_cache.move_to_end(path)
                self._crosshair_pixmap = entry[0]
                # 从 pixmap 缓存的元数据构造 CropResult（保证 bbox/orig 信息不丢失）
                if len(entry) >= 6:
                    _, _, orig_w, orig_h, bbox_x, bbox_y = entry
                    self._crosshair_crop = CropResult(QImage(), bbox_x, bbox_y, orig_w, orig_h, current_mtime)
                elif path in self._crop_cache:
                    self._crosshair_crop = self._crop_cache[path][0]
                else:
                    self._crosshair_crop = self._get_crop(path)
                return
            else:
                del self._crosshair_pixmap_cache[path]
        # 尝试取裁剪结果
        crop = self._get_crop(path)
        if crop is not None:
            self._crosshair_crop = crop
            self._crosshair_pixmap = QPixmap.fromImage(crop.image)
            try:
                mtime = Path(path).stat().st_mtime_ns
            except OSError:
                mtime = 0
            if len(self._crosshair_pixmap_cache) >= self._crosshair_pixmap_cache_max:
                self._crosshair_pixmap_cache.popitem(last=False)
            self._crosshair_pixmap_cache[path] = (self._crosshair_pixmap, mtime, crop.orig_w, crop.orig_h, crop.bbox_x, crop.bbox_y)
        # crop 为 None 时保持上一张 pixmap/crop，后台扫描完成后 _on_scan_done 替换

    def _load_ui_crop(self, path):
        """加载 UI 层：返回 CropResult（QImage），没有则提交后台扫描"""
        return self._get_crop(path)

    # ============================================================
    # 反色
    # ============================================================

    def _get_inverted(self, path, source, is_crosshair=False):
        """获取反色版。易错点2：反色切换不重扫 bbox，直接对裁剪后的图反色"""
        if path in self._inverted_cache:
            try:
                current_mtime = Path(path).stat().st_mtime_ns
            except OSError:
                current_mtime = 0
            if self._inverted_cache[path][1] == current_mtime:
                self._inverted_cache.move_to_end(path)
                return self._inverted_cache[path][0]
            else:
                del self._inverted_cache[path]
        # 生成反色版
        if is_crosshair:
            # crosshair: QPixmap -> QImage -> 反色 -> QPixmap
            image = source.toImage()
            image.invertPixels(QImage.InvertRgb)
            inverted = QPixmap.fromImage(image)
        else:
            # UI: QImage -> 反色
            inverted = source.copy()
            inverted.invertPixels(QImage.InvertRgb)
        try:
            mtime = Path(path).stat().st_mtime_ns
        except OSError:
            mtime = 0
        if len(self._inverted_cache) >= self._inverted_cache_max:
            self._inverted_cache.popitem(last=False)
        self._inverted_cache[path] = (inverted, mtime)
        return inverted

    def set_invert_colors(self, invert):
        if self._invert_colors != invert:
            self._invert_colors = invert
            self.update()

    def toggle_invert_colors(self):
        self.set_invert_colors(not self._invert_colors)
        return self._invert_colors

    @property
    def invert_colors(self):
        return self._invert_colors

    # ============================================================
    # scale / offset（易错点3：scale 防抖 50ms）
    # ============================================================

    def set_scale(self, scale_percent):
        new_scale = max(1.0, min(1000.0, scale_percent))
        if new_scale != self._scale:
            self._scale = new_scale
            self.update()

    def set_offset(self, offset_x, offset_y):
        ox, oy = int(offset_x), int(offset_y)
        if ox == self._offset_x and oy == self._offset_y:
            return
        self._offset_x = ox
        self._offset_y = oy
        self.update()

    def set_display_resolution(self, width, height):
        self._display_w = int(width)
        self._display_h = int(height)
        self.update()

    def set_adjust_overrides(self, sx, sy):
        self._sx_override = float(sx)
        self._sy_override = float(sy)
        self.update()

    def set_sx_adapt_mode(self, mode):
        self._sx_adapt_mode = mode if mode in ("expand", "stretch") else "expand"
        self.update()

    def set_sy_adapt_mode(self, mode):
        self._sy_adapt_mode = mode if mode in ("expand", "stretch") else "expand"
        self.update()

    def _adapt_factors(self):
        # 挡位 / 基准（2K=2560x1440），2K 挡位 = 不缩放 = 1.0
        sx = (self._display_w or self._resource_w) / self._resource_w
        sy = (self._display_h or self._resource_h) / self._resource_h
        if self._sx_override > 0:
            sx = self._sx_override
        if self._sy_override > 0:
            sy = self._sy_override
        return sx, sy

    # ============================================================
    # 可见性 / 屏幕
    # ============================================================

    def set_visible(self, visible):
        self._visible = visible
        if visible:
            self.show()
        else:
            self.hide()

    def set_selected_screen(self, name):
        self._selected_screen_name = name or ""
        self.update_screen_geometry()

    def _resolve_screen(self):
        if self._selected_screen_name:
            for scr in QApplication.screens():
                if (scr.name() or "") == self._selected_screen_name:
                    return scr
        return QApplication.primaryScreen()

    def update_screen_geometry(self):
        screen = self._resolve_screen()
        if screen:
            geometry = screen.geometry()
            self._screen_width = geometry.width()
            self._screen_height = geometry.height()
            self.setGeometry(geometry)
            self.update()


    # ============================================================
    # 渲染
    # ============================================================

    def paintEvent(self, event):
        if not self._visible:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # 渲染顺序（从下到上）：vehicle_ui -> ammo_ui -> crosshair
        if self._vehicle_ui_crop is not None:
            self._paint_ui_layer(painter, self._vehicle_ui_crop, self._vehicle_ui_path)
        if self._ammo_ui_crop is not None:
            self._paint_ui_layer(painter, self._ammo_ui_crop, self._ammo_ui_path)
        if self._crosshair_pixmap is not None and not self._crosshair_pixmap.isNull():
            self._paint_crosshair(painter)

        painter.end()

    def _paint_ui_layer(self, painter, crop, path):
        """绘制 UI 层：全屏整图，用 drawImage(targetRect, image, sourceRect)"""
        if self._invert_colors:
            image = self._get_inverted(path, crop.image, is_crosshair=False)
        else:
            image = crop.image
        # UI 层缩放到屏幕尺寸
        ui_sx = self.width() / crop.orig_w
        ui_sy = self.height() / crop.orig_h
        # 裁剪区域在屏幕上的位置
        target = QRectF(
            crop.bbox_x * ui_sx,
            crop.bbox_y * ui_sy,
            crop.image.width() * ui_sx,
            crop.image.height() * ui_sy
        )
        source = QRectF(0, 0, crop.image.width(), crop.image.height())
        painter.drawImage(target, image, source)

    def _paint_crosshair(self, painter):
        """绘制 crosshair：受 overlay scale/offset 影响，用 drawPixmap(targetRect, pixmap, sourceRect)"""
        if self._invert_colors:
            active_pixmap = self._get_inverted(self._crosshair_path, self._crosshair_pixmap, is_crosshair=True)
        else:
            active_pixmap = self._crosshair_pixmap

        sx, sy = self._adapt_factors()
        base_scale = self._scale / 100.0
        uniform = min(sx, sy)
        w_factor = sx if (self._sx_adapt_mode == "stretch") else uniform
        h_factor = sy if (self._sy_adapt_mode == "stretch") else uniform

        # 原图尺寸（用 crop 的 orig_w/orig_h，或 pixmap 尺寸）
        if self._crosshair_crop is not None:
            orig_w = self._crosshair_crop.orig_w
            orig_h = self._crosshair_crop.orig_h
            bbox_x = self._crosshair_crop.bbox_x
            bbox_y = self._crosshair_crop.bbox_y
        else:
            orig_w = active_pixmap.width()
            orig_h = active_pixmap.height()
            bbox_x = 0
            bbox_y = 0

        # 缩放比例
        scale_x = base_scale * w_factor
        scale_y = base_scale * h_factor

        # 原图在屏幕上的中心位置（offset 使用与 crosshair 内容一致的适配因子）
        center_x = self.width() / 2 + self._offset_x * w_factor
        center_y = self.height() / 2 + self._offset_y * h_factor

        # 原图左上角位置
        orig_left = center_x - (orig_w * scale_x) / 2
        orig_top = center_y - (orig_h * scale_y) / 2

        # 裁剪区域在屏幕上的位置
        target = QRectF(
            orig_left + bbox_x * scale_x,
            orig_top + bbox_y * scale_y,
            active_pixmap.width() * scale_x,
            active_pixmap.height() * scale_y
        )
        source = QRectF(0, 0, active_pixmap.width(), active_pixmap.height())
        painter.drawPixmap(target, active_pixmap, source)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._screen_width = self.width()
        self._screen_height = self.height()


class OverlayRenderer:
    def __init__(self, config_manager, state_machine):
        self.config = config_manager
        self.state = state_machine
        self.overlay = None
        self._suspended = False
        self.state.vehicle_changed.connect(self._on_vehicle_changed)
        self.state.magnification_changed.connect(self._on_state_changed)
        self.state.ammo_type_changed.connect(self._on_state_changed)
        self.state.overlay_settings_changed.connect(self._on_overlay_settings_changed)
        self.state.overlay_toggled.connect(self._on_overlay_toggled)
        self._vehicle_change_in_progress = False

    def shutdown(self):
        """断开全部 StateMachine 信号（关窗/退出时调用）。

        没有断开路径时，重复构造 OverlayRenderer 会让新旧实例的回调叠加——
        Qt 信号持引用，旧实例连同 overlay 窗口一起不释放。
        """
        for sig, slot in [
            (self.state.vehicle_changed, self._on_vehicle_changed),
            (self.state.magnification_changed, self._on_state_changed),
            (self.state.ammo_type_changed, self._on_state_changed),
            (self.state.overlay_settings_changed, self._on_overlay_settings_changed),
            (self.state.overlay_toggled, self._on_overlay_toggled),
        ]:
            try:
                sig.disconnect(slot)
            except TypeError:
                pass  # 未连接
        # M1：停掉 overlay 内的常驻 scanner 线程（closeEvent 之外的双保险，
        # 覆盖 overlay 未经 close 直接丢弃的路径）
        overlay = getattr(self, "overlay", None)
        scanner = getattr(overlay, "_scanner", None) if overlay is not None else None
        if scanner is not None:
            scanner.request_stop()
            scanner.wait(2000)

    def _sync_reference_resolution(self):
        if not self.overlay:
            return
        disp = self.config.get_display_resolution()
        self.overlay.set_display_resolution(disp[0], disp[1])
        if self.config.get_adapt_mode() == "custom":
            self.overlay.set_adjust_overrides(self.config.get_sx_override(), self.config.get_sy_override())
        else:
            self.overlay.set_adjust_overrides(0.0, 0.0)
        self.overlay.set_sx_adapt_mode(self.config.get_sx_adapt_mode())
        self.overlay.set_sy_adapt_mode(self.config.get_sy_adapt_mode())

    def refresh_adapt(self):
        self._sync_reference_resolution()
        self._update_effective_overlay()

    def get_adapt_factors(self):
        if not self.overlay:
            return (1.0, 1.0)
        return self.overlay._adapt_factors()

    def _ensure_overlay(self):
        if not self.overlay:
            # bbox 缓存跟随数据目录（只读安装时与 config 一起降级 %APPDATA%）
            self.overlay = OverlayWindow(config_dir=self.config.config_dir)
            self.overlay.update_screen_geometry()
            self._sync_reference_resolution()
            self._update_crosshair()
            self._update_effective_overlay()
            self.overlay.set_visible(self.state.overlay_visible)
        return self.overlay

    def _cancel_pending_scans(self):
        """取消所有待处理的后台扫描，避免单线程队列阻塞当前状态的图加载。
        已扫描完成的图在缓存中不受影响，下次需要时重新提交即可。"""
        if self.overlay:
            self.overlay._scanner.cancel_all()
            self.overlay._pending_scans.clear()

    def _on_vehicle_changed(self, _name):
        """载具变化：原子事件，做一次全量刷新，抑制随后的 ammo/mag 重复信号。"""
        self._ensure_overlay()
        self._cancel_pending_scans()
        self._vehicle_change_in_progress = True
        self._update_crosshair()
        self._update_effective_overlay()
        # 低优先级预扫描当前载具所有 crosshair 图（插队尾，当前图已插队首）
        self._prescan_current_vehicle()
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._clear_vehicle_suppress)

    def _prescan_current_vehicle(self):
        """预扫描当前载具的所有 crosshair 图（去重），低优先级插队尾"""
        vehicle = self.state.current_vehicle
        if not vehicle:
            return
        vehicles = self.config._config.get("vehicles", {})
        v_data = vehicles.get(vehicle, {})
        paths = set()
        for a_data in v_data.get("ammo_types", {}).values():
            for entry in a_data.get("crosshairs", {}).values():
                rel = entry.get("path", "").replace("\\", "/")
                if rel:
                    paths.add(str(self.config.resolve_resource_path(rel)).replace("\\", "/"))
        if paths:
            self.overlay.prescan_paths(paths)

    def _clear_vehicle_suppress(self):
        self._vehicle_change_in_progress = False

    def _on_state_changed(self):
        """ammo/mag 变化：载具切换期间的重复信号跳过。"""
        if self._vehicle_change_in_progress:
            return
        self._ensure_overlay()
        self._cancel_pending_scans()
        self._update_crosshair()
        self._update_effective_overlay()

    def _on_overlay_settings_changed(self):
        """配置变化：重新加载资源（叠图层开关等）+ 更新绘制参数。"""
        self._ensure_overlay()
        self._update_crosshair()
        self._update_effective_overlay()

    def set_suspended(self, suspended: bool):
        self._suspended = suspended
        if self.overlay:
            self._update_effective_overlay()

    def _update_effective_overlay(self):
        if not self.overlay:
            return
        vehicle = self.state.current_vehicle
        ammo = self.state.current_ammo_type
        mag_idx = self.state.current_magnification_index
        if not vehicle or not ammo:
            if self._suspended:
                self.overlay.setWindowOpacity(self.config.get_overlay_opacity() * 0.5)
            else:
                self.overlay.setWindowOpacity(self.config.get_overlay_opacity())
            return
        effective = self.config.get_effective_overlay(vehicle, ammo, mag_idx)
        self.overlay.set_scale(effective["scale"])
        self.overlay.set_offset(effective["offset_x"], effective["offset_y"])
        opacity = effective.get("opacity", 1.0)
        if self._suspended:
            opacity = opacity * 0.5
        self.overlay.setWindowOpacity(max(0.1, min(1.0, opacity)))

    def _on_overlay_toggled(self, visible):
        self._ensure_overlay()
        self.overlay.set_visible(visible)

    def _update_crosshair(self):
        if not self.overlay:
            return
        vehicle = self.state.current_vehicle
        ammo = self.state.current_ammo_type
        mag_idx = self.state.current_magnification_index
        crosshair_path = self.state.get_current_crosshair_path() or ""
        # 载具 UI 仅当该倍率 overlay_vehicle_ui 为 true 时叠加
        vehicle_ui = ""
        if vehicle and ammo:
            if self.config.get_overlay_vehicle_ui(vehicle, ammo, mag_idx):
                vehicle_ui = self._resolve_ui_path(self.config.get_vehicle_ui(vehicle))
        # 弹种 UI 仅当该倍率 overlay_ammo_ui 为 true 时叠加
        ammo_ui = ""
        if vehicle and ammo:
            if self.config.get_overlay_ammo_ui(vehicle, ammo, mag_idx):
                ammo_ui = self._resolve_ui_path(self.config.get_ammo_ui(vehicle, ammo))
        self.overlay.set_layers(
            crosshair_path=crosshair_path,
            vehicle_ui=vehicle_ui,
            ammo_ui=ammo_ui,
        )

    def _resolve_ui_path(self, rel_path):
        if not rel_path:
            return ""
        rel = rel_path.replace("\\", "/")
        return str(self.config.resolve_resource_path(rel)).replace("\\", "/")

    def _update_scale(self):
        if not self.overlay:
            return
        self.overlay.set_scale(self.config.get_global_scale())

    def _update_offset(self):
        if not self.overlay:
            return
        self.overlay.set_offset(self.config.get_global_offset_x(), self.config.get_global_offset_y())

    def update_scale(self, scale):
        self.config.set_global_scale(scale)
        self._ensure_overlay()
        self._update_effective_overlay()

    def update_offset(self, offset_x, offset_y):
        self.config.set_global_offset(offset_x, offset_y)
        self._ensure_overlay()
        self._update_effective_overlay()

    def show(self):
        """仅显示窗口，不改 state（state 由用户操作通过 state.set_overlay_visible 改变）"""
        self._ensure_overlay()
        self.overlay.set_visible(True)

    def hide(self):
        """仅隐藏窗口，不改 state（关闭时调用不会覆盖用户的准星偏好）"""
        if self.overlay:
            self.overlay.set_visible(False)

    def toggle(self):
        self.state.toggle_overlay()

    def toggle_invert_colors(self):
        self._ensure_overlay()
        return self.overlay.toggle_invert_colors()

