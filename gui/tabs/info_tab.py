"""信息页：标题、简述、免费声明、README链接、吉祥物开关"""
import sys
import os
import subprocess
from pathlib import Path

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QCheckBox, QMessageBox
from PyQt5.QtCore import Qt, QTimer

from core.resource_manager import ResourceManager

APP_VERSION = "V0.0140300086"


class InfoTab(QWidget):
    def __init__(self, resources: ResourceManager, parent=None):
        super().__init__(parent)
        self.resources = resources
        self._mascot = None
        self._build_ui()

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
        if enabled and self._mascot is None:
            self._create_mascot()
        elif not enabled and self._mascot is not None:
            self._mascot.deleteLater()
            self._mascot = None

    def _create_mascot(self):
        from gui.mascot_widget import MascotWidget
        self._mascot = MascotWidget(str(self.resources.get_resources_dir()), self.window())
        self._mascot.show()
        QTimer.singleShot(0, self._position_mascot)

    def _position_mascot(self):
        if self._mascot:
            m = self._mascot
            m.move(self.window().width() - m.width() - 15, self.window().height() - m.height())
            m.raise_()

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
