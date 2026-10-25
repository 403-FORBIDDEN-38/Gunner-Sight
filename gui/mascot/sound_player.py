"""
音效播放器：press/release 双音效，简化逻辑，高频点击不打断。
- press_down: 播放press音效（正在播放则不重启，避免高频点击时音效被切碎）
- press_up: 播放release音效（正在播放则从头播放）
- 移除复杂的_press_ended/_release_played/_release_timer状态机
"""
import os
from gui.mascot.paths import get_mascot_dir
import time

from PyQt5.QtCore import QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

# 资源文件名常量
PRESS_SOUND = "Ya1.mp3"
RELEASE_SOUND = "Ya2.mp3"

# 高频点击防抖：press音效最小播放间隔（ms），小于此间隔不重启
PRESS_MIN_INTERVAL_MS = 150

# 桌宠音效默认音量（0~1）。批次 5：原先三套音量源（SoundPlayer 0.1125 /
# config 默认 0.1125 / ChatBubble 硬编码 10）收敛到这一个常量。
DEFAULT_MASCOT_VOLUME = 0.1125


class SoundPlayer:
    def __init__(self, resources_dir: str, volume: float = DEFAULT_MASCOT_VOLUME):
        self.mascot_dir = get_mascot_dir(resources_dir)
        self.volume = volume
        self._last_press_time = 0  # 上次press播放时间戳（ms）

        self._press_player = QMediaPlayer()
        self._release_player = QMediaPlayer()
        self._press_player.setVolume(int(volume * 100))
        self._release_player.setVolume(int(volume * 100))
        self._press_player.setMedia(QMediaContent(QUrl.fromLocalFile(
            os.path.join(self.mascot_dir, PRESS_SOUND))))
        self._release_player.setMedia(QMediaContent(QUrl.fromLocalFile(
            os.path.join(self.mascot_dir, RELEASE_SOUND))))


    def press_down(self):
        """根源优化：高频点击时不频繁打断press音效。
        如果距离上次press播放 < PRESS_MIN_INTERVAL_MS，且press正在播放，则不重启。
        否则从头播放press。"""
        now = time.monotonic() * 1000
        if now - self._last_press_time < PRESS_MIN_INTERVAL_MS:
            # 高频点击：不重启press，让它播放完
            return
        self._last_press_time = now
        self._press_player.stop()
        self._press_player.setPosition(0)
        self._press_player.setVolume(int(self.volume * 100))
        self._press_player.play()

    def press_up(self):
        """根源优化：release音效直接从头播放，不做复杂的重叠等待。"""
        self._release_player.stop()
        self._release_player.setPosition(0)
        self._release_player.setVolume(int(self.volume * 100))
        self._release_player.play()

    def stop_all(self):
        self._press_player.stop()
        self._release_player.stop()
