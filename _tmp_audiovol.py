import os

p = r'C:\Users\suncheng\Doubao\chats\2026-07-30\new-chat\GunnerSight\gui\mascot\chat_bubble.py'
with open(p, 'r', encoding='utf-8') as f:
    c = f.read()

# 在play()之前再次设置音量，确保setMedia后音量不被重置
old = '''        elif ftype == "audio" and fpath:
            self._audio_player.stop()
            self._audio_player.setMedia(QMediaContent(QUrl.fromLocalFile(fpath)))
            self._audio_player.play()'''

new = '''        elif ftype == "audio" and fpath:
            self._audio_player.stop()
            self._audio_player.setMedia(QMediaContent(QUrl.fromLocalFile(fpath)))
            self._audio_player.setVolume(20)  # 双保险：setMedia后重设音量
            self._audio_player.play()
            print(f"[气泡音频] volume={self._audio_player.volume()} file={os.path.basename(fpath)}")'''

c = c.replace(old, new, 1)

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print('FIXED: setVolume before play + debug print')
