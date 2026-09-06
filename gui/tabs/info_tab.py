"""信息页：标题、简述、免费声明、README链接、吉祥物开关"""
import sys
import os
import subprocess
from pathlib import Path

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QCheckBox, QMessageBox
from PyQt5.QtCore import Qt, QTimer

from core.resource_manager import ResourceManager
from gui.mascot import MascotWidget, ChatBubble, SoundPlayer

APP_VERSION = "V0.0140300090"


class InfoTab(QWidget):
    def __init__(self, config, resources: ResourceManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.resources = resources
        self._mascot = None
        self._bubble = None
        self._sound = None
        self._follow_timer = None
        self._build_ui()
        # 从配置加载吉祥物启用状态
        self.mascot_enable_check.setChecked(self.config.is_mascot_enabled())

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("GunnerSight Overlay")
        title.setObjectName("info_title")
        layout.addWidget(title)

        version_label = QLabel(APP_VERSION)
        version_label.setObjectName("hint_text")
        layout.addWidget(version_label)

        desc = QLabel("屏幕准星辅助软件 — 依程序状态显示对应的炮镜图片，支持载具/弹种/倍率三级切换、全局热键、一键反色、Hold to Aim、外置信息数显（测距）等功能。")
        desc.setObjectName("hint_text")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        free_label = QLabel('本项目为免费工具，本人不收取任何费用。若遇到他人以"代下、安装、指导、内部版"等名义收费，请谨慎判断，谨防信息差，避免为获取本工具额外付费。\n联系方式QQ：3117023693 注明来意')
        free_label.setObjectName("free_notice")
        free_label.setWordWrap(True)
        layout.addWidget(free_label)

        layout.addStretch()

        readme_btn = QPushButton("简述说明")
        readme_btn.setObjectName("link_btn")
        readme_btn.setCursor(Qt.PointingHandCursor)
        readme_btn.clicked.connect(lambda: self._open_doc("README.md"))
        layout.addWidget(readme_btn)

        guide_btn = QPushButton("用户手册")
        guide_btn.setObjectName("link_btn")
        guide_btn.setCursor(Qt.PointingHandCursor)
        guide_btn.clicked.connect(lambda: self._open_doc("USER_GUIDE.md"))
        layout.addWidget(guide_btn)

        self.mascot_enable_check = QCheckBox("召唤惊天一条区")
        self.mascot_enable_check.setChecked(False)
        self.mascot_enable_check.toggled.connect(self._on_mascot_toggled)
        layout.addWidget(self.mascot_enable_check)

    def showEvent(self, event):
        super().showEvent(event)
        if self.mascot_enable_check.isChecked() and self._mascot is None:
            self._create_mascot()

    def _on_mascot_toggled(self, enabled):
        self.config.set_mascot_enabled(enabled)
        if enabled and self._mascot is None:
            self._create_mascot()
        elif not enabled and self._mascot is not None:
            self._shutdown_mascot()

    def _create_mascot(self):
        res_dir = str(self.resources.get_resources_dir())
        parent = self.window()

        self._sound = SoundPlayer(res_dir, volume=0.1125)
        self._bubble = ChatBubble(res_dir, parent=parent)

        self._mascot = MascotWidget(res_dir, parent=parent)
        self._mascot.pressed.connect(self._sound.press_down)
        self._mascot.released.connect(self._sound.press_up)
        self._mascot.clicked.connect(self._on_mascot_clicked)

        self._position_mascot()
        self._mascot.show()
        self._mascot.raise_()

        # 16ms QTimer跟随气泡（≈60fps），气泡显示时start，隐藏时stop（零消耗）
        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(16)
        self._follow_timer.timeout.connect(self._follow_mascot)
        self._bubble.visibility_changed.connect(self._on_bubble_visibility)

    def _shutdown_mascot(self):
        if self._follow_timer:
            self._follow_timer.stop()
            self._follow_timer = None
        if self._bubble:
            self._bubble.hide()
            self._bubble.deleteLater()
            self._bubble = None
        if self._mascot:
            self._mascot.hide()
            self._mascot.deleteLater()
            self._mascot = None
        if self._sound:
            self._sound.stop_all()
            self._sound = None

    def _on_mascot_clicked(self):
        if self._bubble and self._mascot:
            ax, ay = self._anchor()
            self._bubble.show_bubble(ax, ay)
            self._bubble.shake()

    def _anchor(self):
        """气泡锚点：角色水平中心，char_label顶部（随动幅度减半）。"""
        m = self._mascot
        ax = m.x() + m.char_label.x() + m.char_label.width() // 2
        # char_label.y()按压时0→30，取一半使气泡随动幅度减半
        ay = m.y() + int(m.char_label.y() * 0.5)
        return ax, ay

    def _on_bubble_visibility(self, visible):
        """气泡显示时启动跟随定时器，隐藏时停止（零消耗）。"""
        if self._follow_timer:
            if visible:
                self._follow_timer.start()
            else:
                self._follow_timer.stop()

    def _follow_mascot(self):
        if self._bubble and self._bubble.isVisible() and self._mascot:
            ax, ay = self._anchor()
            self._bubble.update_position(ax, ay)

    def _position_mascot(self):
        if self._mascot:
            m = self._mascot
            m.move(self.window().width() - m.width() - 15, self.window().height() - m.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_mascot()

    def _open_doc(self, filename):
        exe_dir = Path(sys.executable).parent
        doc_path = exe_dir / filename
        if not doc_path.exists():
            doc_path = Path(__file__).parent.parent.parent / filename
        if doc_path.exists():
            try:
                os.startfile(str(doc_path))
            except Exception:
                try:
                    subprocess.Popen(['notepad.exe', str(doc_path)])
                except Exception:
                    QMessageBox.information(self, "提示", f"无法打开 {filename}\n路径: {doc_path}")
        else:
            QMessageBox.information(self, "提示", f"{filename} 未找到")
