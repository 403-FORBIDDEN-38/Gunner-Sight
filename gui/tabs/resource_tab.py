"""资源库页：资源列表、图片预览、图片信息"""
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QListWidget,
    QListWidgetItem, QLineEdit, QPushButton, QLabel, QFormLayout,
    QFileDialog, QMessageBox, QInputDialog
)
from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QPixmap, QIcon, QImageReader

from core.config_manager import ConfigManager
from core.resource_manager import ResourceManager
from gui.widgets import OptimizedListWidget, NoWheelSlider


class ResourceTab(QWidget):
    def __init__(self, config: ConfigManager, resources: ResourceManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.resources = resources
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 资源列表
        left_panel = QGroupBox("资源列表")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 12, 8, 8)
        left_layout.setSpacing(5)
        self.resource_search = QLineEdit()
        self.resource_search.setPlaceholderText("搜索资源...")
        left_layout.addWidget(self.resource_search)
        self.resource_list = OptimizedListWidget()
        self.resource_list.setIconSize(QSize(32, 32))
        left_layout.addWidget(self.resource_list, 1)
        res_btn_layout = QHBoxLayout()
        self.import_resource_btn = QPushButton("导入PNG")
        self.import_folder_btn = QPushButton("导入文件夹")
        self.rename_resource_btn = QPushButton("重命名")
        self.delete_resource_btn = QPushButton("删除")
        res_btn_layout.addWidget(self.import_resource_btn)
        res_btn_layout.addWidget(self.import_folder_btn)
        res_btn_layout.addWidget(self.rename_resource_btn)
        res_btn_layout.addWidget(self.delete_resource_btn)
        left_layout.addLayout(res_btn_layout)

        # 预览
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        preview_group = QGroupBox("图片预览")
        preview_layout = QVBoxLayout(preview_group)
        self.resource_preview = QLabel("选择图片预览")
        self.resource_preview.setAlignment(Qt.AlignCenter)
        self.resource_preview.setMinimumSize(250, 250)
        self.resource_preview.setObjectName("preview_box")
        preview_layout.addWidget(self.resource_preview)
        res_scale_row = QHBoxLayout()
        res_scale_row.addWidget(QLabel("缩放:"))
        self.resource_preview_scale = NoWheelSlider(Qt.Horizontal)
        self.resource_preview_scale.setRange(10, 400)
        self.resource_preview_scale.setValue(100)
        self.resource_preview_scale_label = QLabel("100%")
        self.resource_preview_scale_label.setFixedWidth(50)
        res_scale_row.addWidget(self.resource_preview_scale)
        res_scale_row.addWidget(self.resource_preview_scale_label)
        preview_layout.addLayout(res_scale_row)
        right_layout.addWidget(preview_group)

        info_group = QGroupBox("图片信息")
        info_layout = QFormLayout(info_group)
        self.res_info_name = QLabel("-")
        self.res_info_size = QLabel("-")
        self.res_info_dim = QLabel("-")
        self.res_info_format = QLabel("-")
        info_layout.addRow("文件名:", self.res_info_name)
        info_layout.addRow("尺寸:", self.res_info_dim)
        info_layout.addRow("格式:", self.res_info_format)
        info_layout.addRow("文件大小:", self.res_info_size)
        right_layout.addWidget(info_group)
        right_layout.addStretch()

        layout.addWidget(left_panel, 1)
        layout.addWidget(right_panel, 2)

    def connect_signals(self):
        self.import_resource_btn.clicked.connect(self._on_import_resource)
        self.import_folder_btn.clicked.connect(self._on_import_folder)
        self.rename_resource_btn.clicked.connect(self._on_rename_resource)
        self.delete_resource_btn.clicked.connect(self._on_delete_resource)
        self.resource_list.currentItemChanged.connect(self._on_resource_selected)
        self.resource_search.textChanged.connect(self._on_resource_search)
        self.resource_preview_scale.valueChanged.connect(self._update_resource_preview)

    def _refresh_resource_list(self):
        search = self.resource_search.text().lower()
        if not hasattr(self, '_icon_cache'):
            self._icon_cache = {}
        if not hasattr(self, '_icon_queue'):
            self._icon_queue = []
        # 取消正在进行的图标加载
        self._icon_queue.clear()
        self.resource_list.blockSignals(True)
        self.resource_list.clear()
        for name in self.resources.list_resources():
            if search and search not in name.lower():
                continue
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            if name in self._icon_cache:
                item.setIcon(self._icon_cache[name])
            else:
                self._icon_queue.append(name)
            self.resource_list.addItem(item)
        self.resource_list.blockSignals(False)
        # 异步分批加载图标，避免阻塞 UI
        if self._icon_queue:
            QTimer.singleShot(0, self._load_next_icons)

    def _load_next_icons(self):
        """每次加载 2 个图标，然后交还事件循环"""
        batch = 2
        while batch > 0 and self._icon_queue:
            name = self._icon_queue.pop(0)
            try:
                path = self.resources.get_resource_path(name)
                if path and Path(path).exists():
                    reader = QImageReader(str(path))
                    reader.setScaledSize(QSize(32, 32))
                    img = reader.read()
                    if not img.isNull():
                        self._icon_cache[name] = QIcon(QPixmap.fromImage(img))
                        # 更新对应 item 的图标
                        for i in range(self.resource_list.count()):
                            item = self.resource_list.item(i)
                            if item.data(Qt.UserRole) == name:
                                item.setIcon(self._icon_cache[name])
                                break
            except Exception:
                pass
            batch -= 1
        if self._icon_queue:
            QTimer.singleShot(0, self._load_next_icons)

    def _on_resource_search(self, _text):
        self._refresh_resource_list()

    def _on_resource_selected(self, current, _previous):
        if not current:
            return
        name = current.data(Qt.UserRole)
        path = self.resources.get_resource_path(name)
        if not path or not Path(path).exists():
            return
        # 预览 QPixmap 缓存：避免重复选中同一文件时重复从磁盘加载
        if not hasattr(self, '_pixmap_cache'):
            self._pixmap_cache = {}
        if name not in self._pixmap_cache:
            pm = QPixmap(str(path))
            if pm.isNull():
                self.resource_preview.setText("无法加载图片")
                return
            # 简单 LRU：超过 20 张时清空（保留当前）
            if len(self._pixmap_cache) >= 20:
                self._pixmap_cache.clear()
            self._pixmap_cache[name] = pm
        self._current_pixmap = self._pixmap_cache[name]
        self._scaled_cache = None
        self._scaled_cache_key = None
        self.res_info_name.setText(name)
        self.res_info_dim.setText(f"{self._current_pixmap.width()} x {self._current_pixmap.height()}")
        self.res_info_format.setText(Path(path).suffix.upper().lstrip("."))
        size = Path(path).stat().st_size
        self.res_info_size.setText(f"{size / 1024:.1f} KB")
        self._update_resource_preview()

    def _update_resource_preview(self):
        if not hasattr(self, '_current_pixmap') or self._current_pixmap is None or self._current_pixmap.isNull():
            return
        try:
            scale = self.resource_preview_scale.value()
            self.resource_preview_scale_label.setText(f"{scale}%")
            s = scale / 100.0
            # 限制最大预览尺寸，避免大图高缩放导致内存溢出
            max_dim = 4096
            target_w = int(self._current_pixmap.width() * s)
            target_h = int(self._current_pixmap.height() * s)
            if target_w > max_dim or target_h > max_dim:
                ratio = min(max_dim / target_w, max_dim / target_h)
                target_w = int(target_w * ratio)
                target_h = int(target_h * ratio)
            cache_key = (scale, self._current_pixmap.cacheKey())
            if (self._scaled_cache is not None
                    and getattr(self, '_scaled_cache_key', None) == cache_key):
                self.resource_preview.setPixmap(self._scaled_cache)
                return
            if target_w <= 0 or target_h <= 0:
                return
            self._scaled_cache = self._current_pixmap.scaled(
                target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._scaled_cache_key = cache_key
            self.resource_preview.setPixmap(self._scaled_cache)
        except Exception as e:
            self.resource_preview.setText(f"预览失败: {e}")

    def _on_import_resource(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入准星图片", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not path:
            return
        dest_name = self.resources.import_resource(path)
        if dest_name:
            self._refresh_resource_list()
            # 选中新导入的项
            for i in range(self.resource_list.count()):
                if self.resource_list.item(i).data(Qt.UserRole) == dest_name:
                    self.resource_list.setCurrentRow(i)
                    break

    def _on_import_folder(self):
        """FEATURE-2: 选择文件夹批量导入图片（递归包含子文件夹）"""
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if not folder:
            return
        exts = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
        imported = 0
        skipped = 0
        for root, _dirs, files in os.walk(folder):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in exts:
                    continue
                fpath = os.path.join(root, fname)
                dest = self.resources.import_resource(fpath)
                if dest:
                    imported += 1
                else:
                    skipped += 1
        if imported > 0:
            self._refresh_resource_list()
        QMessageBox.information(self, "批量导入完成",
                                "成功导入 %d 个，跳过 %d 个（同名已存在）" % (imported, skipped))

    def _on_rename_resource(self):
        item = self.resource_list.currentItem()
        if not item:
            return
        old = item.data(Qt.UserRole)
        new, ok = QInputDialog.getText(self, "重命名资源", "新名称:", text=old)
        if ok and new.strip() and new != old:
            if self.resources.rename_resource(old, new.strip()):
                # 更新缓存 key
                if hasattr(self, '_icon_cache') and old in self._icon_cache:
                    self._icon_cache[new.strip()] = self._icon_cache.pop(old)
                if hasattr(self, '_pixmap_cache') and old in self._pixmap_cache:
                    self._pixmap_cache[new.strip()] = self._pixmap_cache.pop(old)
                self._refresh_resource_list()

    def _on_delete_resource(self):
        item = self.resource_list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        reply = QMessageBox.question(self, "确认", f"删除资源 '{name}'?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            # 先解绑所有引用该资源的倍率
            unbound = self.config.unbind_crosshair(name)
            self.resources.remove_resource(name)
            # 清除缓存
            if hasattr(self, '_icon_cache'):
                self._icon_cache.pop(name, None)
            if hasattr(self, '_pixmap_cache'):
                self._pixmap_cache.pop(name, None)
            self._refresh_resource_list()
            if unbound > 0:
                QMessageBox.information(self, "提示", f"已删除资源，并解绑 {unbound} 个倍率的准星引用。")

    def refresh(self):
        self._refresh_resource_list()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_resource_list()
