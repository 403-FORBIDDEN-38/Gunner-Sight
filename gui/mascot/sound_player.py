"""
音效播放器：duck音效集（Ya1 press / Ya2 release），预加载无延迟。
- 短按：release与press末尾重叠100ms
- 长按：release在松手时播放
"""
import os
from PyQt5.QtCore import QTimer, QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent


# 资源文件名常量
PRESS_SOUND = "Ya1.mp3"
RELEASE_SOUND = "Ya2.mp3"


class SoundPlayer:
    def __init__(self, resources_dir: str, volume: float = 0.1125):
        self.mascot_dir = os.path.join(resources_dir, "assets/mascot")
        self.volume = volume
        self._pressing = False
        self._press_ended = False
        self._release_played = False
        self._release_timer = QTimer()
        self._release_timer.setSingleShot(True)
        self._release_timer.timeout.connect(self._play_release)

        self._press_player = QMediaPlayer()
        self._release_player = QMediaPlayer()
        self._press_player.setVolume(int(volume * 100))
        self._release_player.setVolume(int(volume * 100))
        self._press_player.setMedia(QMediaContent(QUrl.fromLocalFile(
            os.path.join(self.mascot_dir, PRESS_SOUND))))
        self._release_player.setMedia(QMediaContent(QUrl.fromLocalFile(
            os.path.join(self.mascot_dir, RELEASE_SOUND))))
        self._press_player.mediaStatusChanged.connect(self._on_press_status)

    def set_volume(self, volume):
        self.volume = max(0.0, min(1.0, volume))
        self._press_player.setVolume(int(self.volume * 100))
        self._release_player.setVolume(int(self.volume * 100))

    def _on_press_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self._press_ended = True
            if not self._pressing and not self._release_played:
                self._play_release()

    def press_down(self):
        self._pressing = True
        self._press_ended = False
        self._release_played = False
        self._release_timer.stop()
        self._release_player.stop()
        self._release_player.setPosition(0)
        self._press_player.stop()
        self._press_player.setPosition(0)
        self._press_player.setVolume(int(self.volume * 100))
        self._press_player.play()

    def press_up(self):
        self._pressing = False
        if self._press_ended:
            self._play_release()
            return
        press_dur = self._press_player.duration()
        press_pos = self._press_player.position()
        remain = press_dur - press_pos
        if press_dur > 0 and remain > 100:
            self._release_timer.start(remain - 100)

    def _play_release(self):
        if self._release_played:
            return
        self._release_played = True
        self._release_player.stop()
        self._release_player.setPosition(0)
        self._release_player.setVolume(int(self.volume * 100))
        self._release_player.play()

    def stop_all(self):
        self._pressing = False
        self._release_timer.stop()
        self._press_player.stop()
        self._release_player.stop()
