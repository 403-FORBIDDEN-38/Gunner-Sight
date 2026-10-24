"""信息页：标题、简述、免费声明、README链接、吉祥物开关"""
import base64
import os
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QCheckBox, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.resource_manager import ResourceManager
from gui.mascot import ChatBubble, MascotWidget, SoundPlayer

APP_VERSION = "V0.0140300180"
DEDICATION = "Dedicated to Xiaocheng"


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
        self._connect_ui_signals()
        # 从配置加载吉祥物启用状态
        self.mascot_enable_check.setChecked(self.config.is_mascot_enabled())

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("GUNNER SIGHT")
        title.setObjectName("info_title")
        layout.addWidget(title)

        version_label = QLabel(APP_VERSION)
        version_label.setObjectName("hint_text")
        layout.addWidget(version_label)

        # P5：数据目录可见——只读安装（Program Files 标准用户等）时配置降级到
        # %APPDATA%\GunnerSight，用户需要知道自己的配置/载具库实际存在哪
        data_dir_label = QLabel(f"数据目录: {self.config.config_dir}")
        data_dir_label.setObjectName("hint_text")
        layout.addWidget(data_dir_label)

        dedication_label = QLabel(DEDICATION)
        dedication_label.setObjectName("hint_text")
        layout.addWidget(dedication_label)

        desc = QLabel("屏幕准星辅助软件 — 依程序状态显示对应的炮镜图片，支持载具/弹种/倍率三级切换、一键反色、放大镜、标定测距、角度仪、建队宏等功能。载具导出文件（.gsv）保存在 resources/ 目录下，可直接分享给他人导入使用。")
        desc.setObjectName("hint_text")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        _b64 = "5pys6aG555uu5Li65YWN6LS55bel5YW377yM5pys5Lq65LiN5pS25Y+W5Lu75L2V6LS555So44CC6Iul6YGH5Yiw5LuW5Lq65LulIuS7o+S4i+OAgeWuieijheOAgeaMh+WvvOOAgeWGhemDqOeJiCLnrYnlkI3kuYnmlLbotLnvvIzor7fosKjmhY7liKTmlq3vvIzosKjpmLLkv6Hmga/lt67vvIzpgb/lhY3kuLrojrflj5bmnKzlt6Xlhbfpop3lpJbku5jotLnjgIIK6IGU57O75pa55byPUVHvvJozMTE3MDIzNjkzIOazqOaYjuadpeaEjw=="
        free_label = QLabel(base64.b64decode(_b64).decode("utf-8"))
        free_label.setObjectName("free_notice")
        free_label.setWordWrap(True)
        layout.addWidget(free_label)

        credit_label = QLabel("所有视觉素材版权归原作者所有，仅个人非商用。详见 CREDITS.md。")
        credit_label.setObjectName("hint_text")
        credit_label.setWordWrap(True)
        layout.addWidget(credit_label)

        layout.addStretch()

        self.readme_btn = QPushButton("简述说明")
        self.readme_btn.setObjectName("link_btn")
        self.readme_btn.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.readme_btn)

        self.guide_btn = QPushButton("用户手册")
        self.guide_btn.setObjectName("link_btn")
        self.guide_btn.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.guide_btn)

        self.mascot_enable_check = QCheckBox("召唤惊天一条区")
        self.mascot_enable_check.setChecked(False)
        layout.addWidget(self.mascot_enable_check)

    def _connect_ui_signals(self):
        self.readme_btn.clicked.connect(lambda: self._open_doc("README.md"))
        self.guide_btn.clicked.connect(lambda: self._open_doc("USER_GUIDE.md"))
        self.mascot_enable_check.toggled.connect(self._on_mascot_toggled)

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
