"""资源库页：递归树形目录结构 + 引用关系展示 + 联动维护"""
import shutil
from collections import Counter
from pathlib import Path

from PyQt5.QtCore import QSize, Qt, QUrl
from PyQt5.QtGui import QPixmap
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QFileDialog,
    QMenu,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QPushButton,
    QSlider,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config_manager import ConfigManager
from core.resource_manager import ResourceManager
from gui.widgets import make_group_box, make_button_row


class ResourceTab(QWidget):
    NODE_DIR = "dir"
    NODE_FILE = "file"

    def __init__(self, config: ConfigManager, resources: ResourceManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.resources = resources
        self._expanded_dirs = set()  # 已展开的目录相对路径
        self._reference_index = {}  # {路径: [载具名,...]}
        self._pixmap_cache = {}
        self._build_ui()
        self._connect_ui_signals()

    def _build_ui(self):
        self.setMinimumSize(500, 400)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(3)

        # 左侧：树形资源列表
        left_panel, left_layout = make_group_box("资源库", flat=True)
        left_panel.setMinimumWidth(140)
        left_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        left_layout.setSpacing(5)
        self.resource_search = QLineEdit()
        self.resource_search.setPlaceholderText("搜索资源...")
        left_layout.addWidget(self.resource_search)
        self.resource_tree = QTreeWidget()
        self.resource_tree.setHeaderLabels(["名称", "引用"])
        self.resource_tree.setIconSize(QSize(24, 24))
        self.resource_tree.setMinimumWidth(120)
        self.resource_tree.setTextElideMode(Qt.ElideRight)
        header = self.resource_tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.resource_tree.setRootIsDecorated(True)
        self.resource_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.resource_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        # header去外框
        self.resource_tree.header().setStretchLastSection(False)
        self.resource_tree.header().setMinimumSectionSize(60)
        self.resource_tree.setStyleSheet("QHeaderView::section { border: none; padding: 4px; }")
        self.resource_tree.setMinimumHeight(200)
        left_layout.addWidget(self.resource_tree, 1)
        res_btn_layout = QHBoxLayout()
        self.import_resource_btn = QPushButton("导入PNG")
        res_btn_layout.addWidget(self.import_resource_btn)
        crud_layout, crud_btns = make_button_row([("rename_resource", "重命名"), ("delete_resource", "删除")])
        self.rename_resource_btn = crud_btns["rename_resource"]
        self.delete_resource_btn = crud_btns["delete_resource"]
        res_btn_layout.addLayout(crud_layout)
        left_layout.addLayout(res_btn_layout)

        # 右侧：详情区
        right_panel = QWidget()
        right_panel.setMinimumWidth(140)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 4, 0)
        right_layout.setSpacing(6)

        # 文件详情
        self.file_detail = QWidget()
        file_layout = QVBoxLayout(self.file_detail)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(6)
        preview_group, preview_layout = make_group_box("图片预览", flat=True)
        self.resource_preview = QLabel("选择图片预览")
        self.resource_preview.setAlignment(Qt.AlignCenter)
        self.resource_preview.setMinimumSize(80, 80)
        self.resource_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.resource_preview.setObjectName("preview_box")
        preview_layout.addWidget(self.resource_preview, 1)
        res_scale_row = QHBoxLayout()
        res_scale_row.addWidget(QLabel("缩放:"))
        self.resource_preview_scale = QSlider(Qt.Horizontal)
        self.resource_preview_scale.setRange(10, 400)
        self.resource_preview_scale.setValue(100)
        self.resource_preview_scale_label = QLabel("100%")
        self.resource_preview_scale_label.setFixedWidth(50)
        res_scale_row.addWidget(self.resource_preview_scale)
        res_scale_row.addWidget(self.resource_preview_scale_label)
        preview_layout.addLayout(res_scale_row)
        file_layout.addWidget(preview_group, 1)

        info_group, info_layout = make_group_box("图片信息", layout_cls=QFormLayout)
        info_layout.setVerticalSpacing(2)
        self.res_info_name = QLabel("-")
        self.res_info_name.setWordWrap(True)
        self.res_info_dim = QLabel("-")
        self.res_info_format = QLabel("-")
        self.res_info_size = QLabel("-")
        self.res_info_refs = QLabel("-")
        self.res_info_refs.setWordWrap(True)
        self.res_info_refs.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_layout.addRow("文件名:", self.res_info_name)
        info_layout.addRow("尺寸:", self.res_info_dim)
        info_layout.addRow("格式:", self.res_info_format)
        info_layout.addRow("文件大小:", self.res_info_size)
        info_layout.addRow("被引用:", self.res_info_refs)
        file_layout.addWidget(info_group)

        # 文件夹详情
        self.dir_detail = QWidget()
        dir_layout = QVBoxLayout(self.dir_detail)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(10)
        dir_info_group, dir_info_layout = make_group_box("文件夹信息", layout_cls=QFormLayout, flat=True)
        self.dir_info_name = QLabel("-")
        self.dir_info_file_count = QLabel("-")
        self.dir_info_ref_vehicles = QLabel("-")
        self.dir_info_ref_vehicles.setWordWrap(True)
        self.dir_info_ref_vehicles.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.dir_info_orphan_count = QLabel("-")
        dir_info_layout.addRow("文件夹:", self.dir_info_name)
        dir_info_layout.addRow("图片总数:", self.dir_info_file_count)
        dir_info_layout.addRow("被引用载具:", self.dir_info_ref_vehicles)
        dir_info_layout.addRow("孤儿图片:", self.dir_info_orphan_count)
        dir_layout.addWidget(dir_info_group)
        dir_layout.addStretch()

        right_layout.addWidget(self.file_detail)
        right_layout.addWidget(self.dir_detail)
        right_layout.addStretch()
        self.dir_detail.hide()

        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(right_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        saved = self.config.get_splitter_sizes("resource_tab", [400, 800])
        self.splitter.setSizes(saved)
        self.splitter.splitterMoved.connect(lambda: self.config.set_splitter_sizes(
            "resource_tab", self.splitter.sizes()))
        layout.addWidget(self.splitter)

    def _connect_ui_signals(self):
        self.import_resource_btn.clicked.connect(self._on_import_resource)
        self.rename_resource_btn.clicked.connect(self._on_rename_resource)
        self.delete_resource_btn.clicked.connect(self._on_delete_resource)
        self.resource_tree.currentItemChanged.connect(self._on_resource_selected)
        self.resource_tree.itemExpanded.connect(self._on_item_expanded)
        self.resource_tree.itemCollapsed.connect(self._on_item_collapsed)
        self.resource_search.textChanged.connect(self._on_resource_search)
        self.resource_preview_scale.valueChanged.connect(self._update_resource_preview)

    def _rebuild_reference_index(self):
        """重建引用倒排索引"""
        self._reference_index = self.config.get_crosshair_reference_index()

    def _get_ref_count(self, path: str) -> int:
        """获取某路径被引用的载具数（去重）"""
        return len(set(self._reference_index.get(path, [])))

    def _get_ref_text(self, path: str) -> str:
        """获取引用文本：载具名(计数)，多个用顿号分隔"""
        vehicles = self._reference_index.get(path, [])
        if not vehicles:
            return "0"
        counter = Counter(vehicles)
        parts = []
        for vname, cnt in counter.most_common():
            if cnt > 1:
                parts.append(f"{vname}({cnt}处)")
            else:
                parts.append(vname)
        return "、".join(parts)

    def _get_dir_aggregate(self, dir_path: str) -> dict:
        """获取文件夹聚合信息：文件总数、引用载具去重、孤儿数"""
        all_resources = self.resources.list_resources()
        prefix = dir_path + "/" if dir_path else ""
        files = [f for f in all_resources if f.startswith(prefix) and "/" not in f[len(prefix):]]
        all_vehicles = set()
        orphan_count = 0
        for f in files:
            refs = self._reference_index.get(f, [])
            if refs:
                all_vehicles.update(refs)
            else:
                orphan_count += 1
        return {
            "files": files,
            "file_count": len(files),
            "ref_vehicles": sorted(all_vehicles),
            "orphan_count": orphan_count,
        }

    def _build_dir_tree(self, all_resources: list[str]) -> dict:
        """构建目录树：{目录名: {"dirs": {...}, "files": [路径,...]}}"""
        root = {"dirs": {}, "files": []}
        for rel_path in all_resources:
            parts = Path(rel_path).parts
            node = root
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    node["files"].append(rel_path)
                else:
                    if part not in node["dirs"]:
                        node["dirs"][part] = {"dirs": {}, "files": []}
                    node = node["dirs"][part]
        return root

    def _create_tree_item(self, name: str, node: dict, parent_path: str, search: str = "") -> QTreeWidgetItem | None:
        """递归创建树形节点。search非空时过滤不打散，匹配目录自动展开。"""
        current_path = f"{parent_path}/{name}" if parent_path else name

        # 搜索模式：过滤，不打散
        if search:
            has_match = any(search in f.lower() for f in node["files"])
            matching_children = []
            for dname, dnode in node["dirs"].items():
                child = self._create_tree_item(dname, dnode, current_path, search)
                if child is not None:
                    matching_children.append(child)
                    has_match = True
            if not has_match:
                return None

        # 计算目录级引用聚合（含子目录递归）
        all_vehicles = set()
        orphan_count = 0
        for f in node["files"]:
            refs = self._reference_index.get(f, [])
            if refs:
                all_vehicles.update(refs)
            else:
                orphan_count += 1
        for dnode in node["dirs"].values():
            agg = self._collect_dir_refs(dnode)
            all_vehicles.update(agg["vehicles"])
            orphan_count += agg["orphans"]

        ref_text = f"{len(all_vehicles)}载具" if all_vehicles else "0"
        dir_item = QTreeWidgetItem([name, ref_text])
        dir_item.setData(0, Qt.UserRole, (self.NODE_DIR, current_path))

        # 子目录
        if search:
            for child in matching_children:
                dir_item.addChild(child)
        else:
            for dname in sorted(node["dirs"].keys()):
                child = self._create_tree_item(dname, node["dirs"][dname], current_path)
                if child is not None:
                    dir_item.addChild(child)

        # 文件（搜索时只显示匹配的）
        files_to_show = node["files"]
        if search:
            files_to_show = [f for f in node["files"] if search in f.lower()]
        for f in sorted(files_to_show):
            fname = Path(f).name
            ref_count = self._get_ref_count(f)
            file_item = QTreeWidgetItem([fname, str(ref_count)])
            file_item.setData(0, Qt.UserRole, (self.NODE_FILE, f))
            if ref_count == 0:
                file_item.setForeground(0, Qt.gray)
            dir_item.addChild(file_item)

        return dir_item

    def _collect_dir_refs(self, node: dict) -> dict:
        """递归收集目录下所有文件的引用载具和孤儿数"""
        vehicles = set()
        orphans = 0
        for f in node["files"]:
            refs = self._reference_index.get(f, [])
            if refs:
                vehicles.update(refs)
            else:
                orphans += 1
        for dnode in node["dirs"].values():
            agg = self._collect_dir_refs(dnode)
            vehicles.update(agg["vehicles"])
            orphans += agg["orphans"]
        return {"vehicles": vehicles, "orphans": orphans}

    def _refresh_tree(self):
        """刷新树形列表（保存并恢复选中状态，避免clear后选中丢失导致拟物框）"""
        search = self.resource_search.text().lower().strip()
        # 保存当前选中路径（clear前）
        saved_path = None
        cur = self.resource_tree.currentItem()
        if cur:
            saved_path = cur.data(0, Qt.UserRole)
        self._rebuild_reference_index()
        all_resources = self.resources.list_resources()
        dir_tree = self._build_dir_tree(all_resources)

        self.resource_tree.blockSignals(True)
        self.resource_tree.clear()

        if search:
            # 搜索模式：过滤分组，不打散
            for name in sorted(dir_tree["dirs"].keys()):
                item = self._create_tree_item(name, dir_tree["dirs"][name], "", search)
                if item is not None:
                    self.resource_tree.addTopLevelItem(item)
            # 根目录文件
            for f in sorted(dir_tree["files"]):
                if search in f.lower():
                    item = QTreeWidgetItem([Path(f).name, str(self._get_ref_count(f))])
                    item.setData(0, Qt.UserRole, (self.NODE_FILE, f))
                    if self._get_ref_count(f) == 0:
                        item.setForeground(0, Qt.gray)
                    self.resource_tree.addTopLevelItem(item)
        else:
            # 正常模式：递归树形
            for name in sorted(dir_tree["dirs"].keys()):
                item = self._create_tree_item(name, dir_tree["dirs"][name], "")
                if item is not None:
                    self.resource_tree.addTopLevelItem(item)
            # 根目录文件
            for f in sorted(dir_tree["files"]):
                item = QTreeWidgetItem([Path(f).name, str(self._get_ref_count(f))])
                item.setData(0, Qt.UserRole, (self.NODE_FILE, f))
                if self._get_ref_count(f) == 0:
                    item.setForeground(0, Qt.gray)
                self.resource_tree.addTopLevelItem(item)

        self.resource_tree.blockSignals(False)
        # 递归展开：搜索模式展开所有目录；正常模式恢复用户展开状态
        self._apply_expand_state(self.resource_tree.invisibleRootItem(), bool(search))
        # 恢复选中项（setCurrentItem同时设current和selected，消除孤立current指示器）
        if saved_path:
            self._restore_selected_item(self.resource_tree.invisibleRootItem(), saved_path)

    def _restore_selected_item(self, parent, target):
        """递归查找并选中目标路径的item"""
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, Qt.UserRole) == target:
                self.resource_tree.setCurrentItem(child)
                return True
            if self._restore_selected_item(child, target):
                return True
        return False

    def _apply_expand_state(self, item, is_search: bool):
        """递归设置展开状态"""
        for i in range(item.childCount()):
            child = item.child(i)
            node_type, path = child.data(0, Qt.UserRole)
            if node_type == self.NODE_DIR:
                if is_search or path in self._expanded_dirs:
                    self.resource_tree.expandItem(child)
                self._apply_expand_state(child, is_search)

    def _on_item_expanded(self, item):
        node_type, path = item.data(0, Qt.UserRole)
        if node_type == self.NODE_DIR:
            self._expanded_dirs.add(path)

    def _on_item_collapsed(self, item):
        node_type, path = item.data(0, Qt.UserRole)
        if node_type == self.NODE_DIR:
            self._expanded_dirs.discard(path)

    def _on_resource_search(self, _text):
        self._refresh_tree()

    def _on_resource_selected(self, current, _previous):
        if not current:
            return
        node_type, path = current.data(0, Qt.UserRole)
        if node_type == self.NODE_FILE:
            self._show_file_detail(path)
        elif node_type == self.NODE_DIR:
            self._show_dir_detail(path)

    def _show_file_detail(self, path: str):
        self.dir_detail.hide()
        self.file_detail.show()

        full_path = self.resources.get_resource_path(path)
        if not full_path or not Path(full_path).exists():
            self.resource_preview.setText("文件不存在")
            return

        if path not in self._pixmap_cache:
            pm = QPixmap(str(full_path))
            if pm.isNull():
                self.resource_preview.setText("无法加载图片")
                return
            if len(self._pixmap_cache) >= 20:
                self._pixmap_cache.clear()
            self._pixmap_cache[path] = pm
        self._current_pixmap = self._pixmap_cache[path]
        self._scaled_cache = None
        self._scaled_cache_key = None

        self.res_info_name.setText(path)
        self.res_info_dim.setText(f"{self._current_pixmap.width()} x {self._current_pixmap.height()}")
        self.res_info_format.setText(Path(full_path).suffix.upper().lstrip("."))
        size = Path(full_path).stat().st_size
        self.res_info_size.setText(f"{size / 1024:.1f} KB")
        self.res_info_refs.setText(self._get_ref_text(path))
        self._update_resource_preview()

    def _show_dir_detail(self, dir_path: str):
        self.file_detail.hide()
        self.dir_detail.show()
        agg = self._get_dir_aggregate(dir_path)
        self.dir_info_name.setText(dir_path if dir_path else "(根目录)")
        self.dir_info_file_count.setText(str(agg["file_count"]))
        self.dir_info_ref_vehicles.setText("、".join(agg["ref_vehicles"]) if agg["ref_vehicles"] else "无")
        self.dir_info_orphan_count.setText(str(agg["orphan_count"]))

    def _update_resource_preview(self):
        if not hasattr(self, '_current_pixmap') or self._current_pixmap is None or self._current_pixmap.isNull():
            return
        try:
            scale = self.resource_preview_scale.value()
            self.resource_preview_scale_label.setText(f"{scale}%")
            s = scale / 100.0
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
            self._refresh_tree()
            for i in range(self.resource_tree.topLevelItemCount()):
                item = self.resource_tree.topLevelItem(i)
                node_type, p = item.data(0, Qt.UserRole)
                if p == dest_name:
                    self.resource_tree.setCurrentItem(item)
                    break

    def _on_rename_resource(self):
        item = self.resource_tree.currentItem()
        if not item:
            return
        node_type, path = item.data(0, Qt.UserRole)
        old_name = Path(path).name if node_type == self.NODE_FILE else Path(path).name

        new_name, ok = QInputDialog.getText(self, "重命名", "新名称:", text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()

        if node_type == self.NODE_FILE:
            self._rename_file(path, new_name)
        else:
            self._rename_dir(path, new_name)

    def _rename_file(self, old_path: str, new_name: str):
        """重命名单个文件：先改文件，成功后更新config引用"""
        # 检查非法字符
        invalid_chars = '<>:"/\\|?*'
        if any(c in new_name for c in invalid_chars):
            QMessageBox.warning(self, "失败", f"文件名包含非法字符: {''.join(c for c in new_name if c in invalid_chars)}")
            return
        new_path = str(Path(old_path).parent / new_name).replace("\\", "/")
        if new_path == ".":
            new_path = new_name

        new_abs = self.resources.resources_dir / new_path
        if new_abs.exists():
            QMessageBox.warning(self, "失败", f"目标文件已存在: {new_path}")
            return

        if not self.resources.rename_resource(old_path, new_path):
            QMessageBox.warning(self, "失败", f"重命名失败: {new_path}")
            return

        ref_count = self.config.rename_crosshair_path(old_path, new_path)
        self._pixmap_cache.pop(old_path, None)
        self._refresh_tree()

        if ref_count > 0:
            QMessageBox.information(self, "完成", f"已重命名，并同步更新 {ref_count} 处载具引用。")
        else:
            QMessageBox.information(self, "完成", "已重命名（该文件未被任何载具引用）。")

    def _rename_dir(self, old_dir: str, new_name: str):
        """重命名文件夹：递归移动所有文件 + 批量更新config引用"""
        new_dir = str(Path(old_dir).parent / new_name).replace("\\", "/")
        if new_dir == ".":
            new_dir = new_name

        old_dir_abs = self.resources.resources_dir / old_dir
        new_dir_abs = self.resources.resources_dir / new_dir
        if not old_dir_abs.exists():
            QMessageBox.warning(self, "失败", f"文件夹不存在: {old_dir}")
            return
        if new_dir_abs.exists():
            QMessageBox.warning(self, "失败", f"目标文件夹已存在: {new_dir}")
            return

        # 收集该目录下所有文件
        all_resources = self.resources.list_resources()
        prefix = old_dir + "/"
        files_to_move = [f for f in all_resources if f.startswith(prefix)]

        if not files_to_move:
            # 空目录，直接改名
            old_dir_abs.rename(new_dir_abs)
            self._refresh_tree()
            QMessageBox.information(self, "完成", "已重命名空文件夹。")
            return

        # 移动文件 + 更新引用
        moved_count = 0
        ref_updated = 0
        try:
            new_dir_abs.mkdir(parents=True, exist_ok=True)
            for old_file in files_to_move:
                rel_sub = old_file[len(prefix):]
                new_file = f"{new_dir}/{rel_sub}"
                old_abs = self.resources.resources_dir / old_file
                new_abs = self.resources.resources_dir / new_file
                new_abs.parent.mkdir(parents=True, exist_ok=True)
                old_abs.rename(new_abs)
                moved_count += 1
                ref_updated += self.config.rename_crosshair_path(old_file, new_file)
            # 删除空的旧目录树
            import shutil
            shutil.rmtree(old_dir_abs, ignore_errors=True)
        except Exception as e:
            QMessageBox.critical(self, "失败", f"重命名文件夹时出错: {e}\n已移动 {moved_count} 个文件。")
            self._refresh_tree()
            return

        self.resources._invalidate_resources_cache()
        self._refresh_tree()
        QMessageBox.information(self, "完成",
                                f"已重命名文件夹，移动 {moved_count} 个文件，同步更新 {ref_updated} 处载具引用。")

    def _on_delete_resource(self):
        item = self.resource_tree.currentItem()
        if not item:
            return
        node_type, path = item.data(0, Qt.UserRole)

        if node_type == self.NODE_FILE:
            self._delete_file(path)
        else:
            self._delete_dir(path)

    def _delete_file(self, path: str):
        ref_text = self._get_ref_text(path)
        ref_count = self._get_ref_count(path)

        if ref_count > 0:
            reply = QMessageBox.question(
                self, "确认删除",
                f"该图片被 {ref_count} 辆载具引用：\n{ref_text}\n\n删除后这些载具将失去准星。确认删除？",
                QMessageBox.Yes | QMessageBox.No)
        else:
            reply = QMessageBox.question(
                self, "确认删除",
                "该图片未被任何载具引用（孤儿文件）。确认删除？",
                QMessageBox.Yes | QMessageBox.No)

        if reply != QMessageBox.Yes:
            return

        unbound = self.config.unbind_crosshair(path)
        self.resources.remove_resource(path)
        self._pixmap_cache.pop(path, None)
        self._refresh_tree()

        if unbound > 0:
            QMessageBox.information(self, "完成", f"已删除，并解绑 {unbound} 处载具引用。")

    def _delete_dir(self, dir_path: str):
        agg = self._get_dir_aggregate(dir_path)
        files = agg["files"]
        ref_vehicles = agg["ref_vehicles"]

        if ref_vehicles:
            reply = QMessageBox.question(
                self, "确认删除",
                f"该文件夹含 {len(files)} 张图片，被 {len(ref_vehicles)} 辆载具引用：\n"
                f"{'、'.join(ref_vehicles[:10])}{'...' if len(ref_vehicles) > 10 else ''}\n\n"
                f"删除后这些载具将失去准星。确认删除整个文件夹？",
                QMessageBox.Yes | QMessageBox.No)
        else:
            reply = QMessageBox.question(
                self, "确认删除",
                f"该文件夹含 {len(files)} 张图片，均未被引用（孤儿）。确认删除整个文件夹？",
                QMessageBox.Yes | QMessageBox.No)

        if reply != QMessageBox.Yes:
            return

        # 递归收集所有文件（含子目录）
        all_resources = self.resources.list_resources()
        prefix = dir_path + "/"
        all_files = [f for f in all_resources if f.startswith(prefix)]

        unbound_total = 0
        for f in all_files:
            unbound_total += self.config.unbind_crosshair(f)
            self.resources.remove_resource(f)
            self._pixmap_cache.pop(f, None)

        # 删除空目录
        import shutil
        dir_abs = self.resources.resources_dir / dir_path
        shutil.rmtree(dir_abs, ignore_errors=True)
        self.resources._invalidate_resources_cache()
        self._refresh_tree()

        QMessageBox.information(self, "完成",
                                f"已删除文件夹（{len(all_files)} 张图片），解绑 {unbound_total} 处载具引用。")

    def _on_tree_context_menu(self, pos):
        item = self.resource_tree.itemAt(pos)
        menu = QMenu(self)
        action_refresh = menu.addAction("刷新")
        if item:
            node_data = item.data(0, Qt.UserRole)
            if node_data and node_data[0] in (self.NODE_FILE, self.NODE_DIR):
                rel_path = node_data[1]
                menu.addSeparator()
                action_open = menu.addAction("打开所在文件夹")
                action_copy = menu.addAction("复制路径")
                menu.addSeparator()
                action_delete = menu.addAction("删除")
        chosen = menu.exec_(self.resource_tree.viewport().mapToGlobal(pos))
        if chosen == action_refresh:
            self._refresh_tree()
        elif item and chosen == action_open:
            node_data = item.data(0, Qt.UserRole)
            rel_path = node_data[1]
            full_path = Path(self.resources.resources_dir) / rel_path
            if full_path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(full_path.parent if full_path.is_file() else full_path)))
        elif item and chosen == action_copy:
            node_data = item.data(0, Qt.UserRole)
            rel_path = node_data[1]
            full_path = Path(self.resources.resources_dir) / rel_path
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(str(full_path))
        elif item and chosen == action_delete:
            node_data = item.data(0, Qt.UserRole)
            rel_path = node_data[1]
            full_path = Path(self.resources.resources_dir) / rel_path
            is_dir = full_path.is_dir()
            label = "文件夹" if is_dir else "文件"
            reply = QMessageBox.question(self, "确认删除",
                                         f"确定删除{label} '{rel_path}'？",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                try:
                    if is_dir:
                        shutil.rmtree(full_path)
                    else:
                        full_path.unlink()
                    self.resources._invalidate_resources_cache()
                    self._refresh_tree()
                except Exception as e:
                    QMessageBox.warning(self, "删除失败", str(e))

    def refresh(self):
        self._refresh_tree()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_tree()
