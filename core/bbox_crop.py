"""
透明区域裁剪模块

功能：
- find_opaque_bbox: 扫描 QImage 的非透明区域 bounding box
- CropResult: 裁剪结果（裁剪后 QImage + bbox 偏移 + 原图尺寸）
- BboxCache: 预扫描 bbox 缓存（json 持久化，避免重复扫描）
- BboxScanner: 后台 QThread 扫描，支持取消，扫描完发信号

设计原则：
- QImage 非线程安全：后台线程独立加载，不复用主线程实例
- 任务可取消：切载具时取消旧任务
- 裁剪比例 < 10% 跳过裁剪，避免复制开销大于收益
- 预扫描缓存：启动后台扫所有图存 json，之后切换跳过 250ms 扫描
- 缓存有效性以内容 sha256 为最终判据（mtime 只作快路径）：mtime 在
  zip（2 秒精度、向下取偶）和 git clone（不保存 mtime）之后必然失真，
  只认 mtime 会让一份正确的预计算在别人机器上全部失效
"""
import hashlib
import json
import threading
from pathlib import Path

from PyQt5.QtCore import QMutex, QThread, QWaitCondition, pyqtSignal
from PyQt5.QtGui import QImage

from core.logger import logger


def _file_sha256(path, chunk=1 << 16):
    """流式计算文件内容的 sha256（小写十六进制）。读失败返回 None。

    作为缓存有效性的最终判据，替代不可移植的 mtime。开销可忽略：
    371 张 PNG（约 10.6MB）全量算完约 48ms，单张约 0.1ms；而被它
    省掉的一次全量 bbox 重扫是 40~76 秒。
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(chunk), b""):
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


def find_opaque_bbox(img, alpha_threshold=0):
    """扫描非透明区域的 bounding box，返回 (x, y, w, h)，全透明返回 None"""
    if img.isNull():
        return None
    if img.format() != QImage.Format_ARGB32:
        img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    bpl = img.bytesPerLine()
    ptr = img.bits()
    ptr.setsize(img.byteCount())
    data = bytes(ptr)

    min_y = max_y = -1
    for y in range(h):
        row = data[y * bpl: y * bpl + w * 4]
        if any(row[x * 4 + 3] > alpha_threshold for x in range(w)):
            if min_y == -1:
                min_y = y
            max_y = y
    if min_y == -1:
        return None

    min_x, max_x = w, -1
    for y in range(min_y, max_y + 1):
        row = data[y * bpl: y * bpl + w * 4]
        for x in range(w):
            if row[x * 4 + 3] > alpha_threshold:
                if x < min_x:
                    min_x = x
                break
        for x in range(w - 1, -1, -1):
            if row[x * 4 + 3] > alpha_threshold:
                if x > max_x:
                    max_x = x
                break
    return (min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


class CropResult:
    """裁剪结果：裁剪后的 QImage + bbox 偏移 + 原图尺寸"""
    __slots__ = ("image", "bbox_x", "bbox_y", "orig_w", "orig_h", "mtime", "cropped")

    def __init__(self, image, bbox_x, bbox_y, orig_w, orig_h, mtime):
        self.image = image
        self.bbox_x = bbox_x
        self.bbox_y = bbox_y
        self.orig_w = orig_w
        self.orig_h = orig_h
        self.mtime = mtime
        self.cropped = (
            bbox_x > 0 or bbox_y > 0
            or bbox_x + image.width() < orig_w
            or bbox_y + image.height() < orig_h
        )

    @property
    def crop_ratio(self):
        if self.orig_w <= 0 or self.orig_h <= 0:
            return 0.0
        orig_pixels = self.orig_w * self.orig_h
        crop_pixels = self.image.width() * self.image.height()
        return 1.0 - crop_pixels / orig_pixels


def _crop_with_bbox(img, bbox, orig_w, orig_h, mtime, min_crop_ratio=0.10):
    """用预计算的 bbox 裁剪，跳过扫描"""
    bx, by, bw, bh = bbox
    pad = 2
    bx = max(0, bx - pad)
    by = max(0, by - pad)
    bw = min(orig_w - bx, bw + pad * 2)
    bh = min(orig_h - by, bh + pad * 2)
    crop_ratio = 1.0 - (bw * bh) / (orig_w * orig_h)
    if crop_ratio < min_crop_ratio:
        return CropResult(img, 0, 0, orig_w, orig_h, mtime)
    cropped = img.copy(bx, by, bw, bh)
    img = None
    return CropResult(cropped, bx, by, orig_w, orig_h, mtime)


def load_and_crop(path, alpha_threshold=0, min_crop_ratio=0.10):
    """加载图片并扫描+裁剪。全透明返回 None"""
    p = Path(path)
    if not p.exists():
        return None
    img = QImage(str(p))
    if img.isNull():
        return None
    if img.format() != QImage.Format_ARGB32:
        img = img.convertToFormat(QImage.Format_ARGB32)
    orig_w, orig_h = img.width(), img.height()
    try:
        mtime = p.stat().st_mtime_ns
    except OSError:
        mtime = 0
    bbox = find_opaque_bbox(img, alpha_threshold)
    if bbox is None:
        img = None
        return None
    return _crop_with_bbox(img, bbox, orig_w, orig_h, mtime, min_crop_ratio), bbox


def load_with_bbox(path, bbox, min_crop_ratio=0.10):
    """用预计算的 bbox 加载+裁剪，跳过扫描。返回 CropResult 或 None"""
    p = Path(path)
    if not p.exists():
        return None
    img = QImage(str(p))
    if img.isNull():
        return None
    if img.format() != QImage.Format_ARGB32:
        img = img.convertToFormat(QImage.Format_ARGB32)
    orig_w, orig_h = img.width(), img.height()
    try:
        mtime = p.stat().st_mtime_ns
    except OSError:
        mtime = 0
    return _crop_with_bbox(img, bbox, orig_w, orig_h, mtime, min_crop_ratio)


class BboxCache:
    """预扫描 bbox 缓存，json 持久化到 config/bbox_cache.json。内部用相对路径存储，兼容源码版和打包版。"""

    def __init__(self, cache_path, resources_dir=None):
        self._path = Path(cache_path)
        self._res_dir = Path(resources_dir) if resources_dir else self._path.parent
        self._data = {}
        self._dirty = False
        # M2：跨线程锁。主线程 get()/has() 与扫描线程 get()/set()/save() 并发访问
        # self._data，json.dump 迭代期 dict 增删可抛 RuntimeError（此前被 scanner
        # 的 except 吞掉，缓存静默丢失）。RLock：has() 内部调 get() 需可重入。
        self._lock = threading.RLock()
        self.load()
        self.cleanup()

    def _to_rel(self, path):
        """绝对路径转相对路径（相对于 resources 目录），失败则返回原路径"""
        try:
            return str(Path(path).resolve().relative_to(self._res_dir.resolve())).replace("\\", "/")
        except (ValueError, OSError):
            return str(path).replace("\\", "/")

    def _to_abs(self, rel_path):
        """相对路径转绝对路径"""
        p = Path(rel_path)
        if p.is_absolute():
            return str(p).replace("\\", "/")
        return str(self._res_dir / rel_path).replace("\\", "/")

    def load(self):
        with self._lock:
            if not self._path.exists():
                return
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
                self._path.unlink(missing_ok=True)

    def cleanup(self):
        """删除孤儿条目，并把 mtime 失真而内容未变的条目就地自愈。

        三层判断（启动时一次跑完）：
        1. 源文件不存在 → 删（孤儿）
        2. mtime 与记录一致 → 什么都不做（本机日常路径，零 hash 开销）
        3. mtime 不一致 → 算内容 sha256：
           - 一致 → 只是 zip 解压 / git clone 改写了时间戳，写回新 mtime（自愈）
           - 不一致 → 图真换了，条目保留（get() 会判失效，重扫后 set() 覆盖）

        **刻意不因 mtime 不符而删条目**：mtime 在分发后必然失真，若按它删，
        一份正确的出厂预计算会在别人机器上第一次启动、第一个 get() 之前
        就被整份清空并写回空文件。

        自愈必须在这里做（而不是只靠 get()）：全部命中的情况下扫描线程
        不会启动，get() 里的 dirty 没有任何时机落盘，下次启动又要重算一遍。
        """
        with self._lock:
            removed = 0
            healed = 0
            for rel in list(self._data.keys()):
                p = Path(self._to_abs(rel))
                try:
                    st = p.stat()
                except OSError:
                    del self._data[rel]
                    removed += 1
                    continue
                entry = self._data[rel]
                if not isinstance(entry, dict):
                    del self._data[rel]
                    removed += 1
                    continue
                if entry.get("mtime") == st.st_mtime_ns:
                    continue
                expected = entry.get("sha256")
                if not expected:
                    continue  # 旧版条目无指纹：留给 get() 判未命中 → 重扫覆盖
                if _file_sha256(self._to_abs(rel)) == expected:
                    entry["mtime"] = st.st_mtime_ns
                    healed += 1
            if removed or healed:
                self._dirty = True
                self.save()

    def save(self):
        with self._lock:
            if not self._dirty:
                return
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, separators=(",", ":"))
                self._dirty = False
            except OSError:
                pass

    def get(self, path, mtime):
        """查询缓存，命中返回 bbox tuple，否则 None。

        两级判据：
        1. mtime 完全一致 → 快路径，不读文件（本机日常路径，零额外开销）
        2. mtime 不一致 → 算内容 sha256 比对。一致说明只是分发/复制导致
           时间戳失真，命中并把新 mtime 写回缓存（自愈，每个文件只付一次，
           之后回到快路径）；不一致说明图真的换过，返回 None 让调用方重扫。

        结构异常、以及旧版遗留的「无 sha256」条目一律按未命中处理。
        """
        rel = self._to_rel(path)
        with self._lock:
            entry = self._data.get(rel)
            if not isinstance(entry, dict):
                if entry is not None:
                    del self._data[rel]
                    self._dirty = True
                return None
            bbox = entry.get("bbox")
            if not (isinstance(bbox, list) and len(bbox) == 4):
                return None
            if entry.get("mtime") == mtime:
                return tuple(bbox)
            expected = entry.get("sha256")
            if not expected:
                return None
        # 文件 I/O 放在锁外：get() 会从主线程调用（切图），
        # 持锁读盘会连带阻塞扫描线程
        actual = _file_sha256(self._to_abs(rel))
        if actual is None or actual != expected:
            return None
        with self._lock:
            entry = self._data.get(rel)
            if not isinstance(entry, dict) or entry.get("sha256") != expected:
                return None  # 期间被删/被覆盖，本轮不认
            entry["mtime"] = mtime
            self._dirty = True
            return tuple(entry["bbox"])

    def set(self, path, bbox, mtime, orig_size, sha256=None):
        """写入缓存。sha256 为空时当场计算（调用方是扫描线程，不在主线程）"""
        rel = self._to_rel(path)
        if sha256 is None:
            sha256 = _file_sha256(self._to_abs(rel))
        with self._lock:
            entry = {
                "bbox": list(bbox),
                "mtime": mtime,
                "orig_size": list(orig_size),
            }
            if sha256:
                entry["sha256"] = sha256
            self._data[rel] = entry
            self._dirty = True

    def has(self, path, mtime):
        """缓存中是否有该文件的有效 bbox（判据完全同 get）。

        不额外加锁：get() 自身已是原子读，外层再持锁会让锁外那段
        文件 I/O 重新落回锁内（prescan_paths 在主线程批量调用本方法）。
        """
        return self.get(path, mtime) is not None

    def all_paths(self):
        with self._lock:
            return [self._to_abs(rel) for rel in self._data]


class BboxScanner(QThread):
    """
    后台扫描 bbox 的 QThread。
    - 单线程串行扫描
    - 支持按 task_id 取消
    - 支持预计算 bbox（跳过扫描）
    - 扫描完发 scan_done 信号，自动写回 BboxCache

    M1 常驻模式：线程只由 request_stop() 退出，队列空时在 QWaitCondition 上
    等待，永不因空闲自退。任务到达 wakeOne 唤醒。这从根上消灭了旧起停模式
    的竞态——旧模式 isRunning() 在 run() 判空退出后、finished 前仍为 True，
    submit 看到 True 不 start()，任务成孤儿（_pending_scans 永久不清、
    本次会话该路径加载不出图）；且 submit 无法区分「线程正在跑」与「线程
    正在死」，wait() 旧线程会误等一个健康线程（每次 submit 卡满超时）。
    """

    scan_done = pyqtSignal(str, object)  # path, CropResult（或 None）

    def __init__(self, bbox_cache=None, parent=None):
        super().__init__(parent)
        self._tasks = []  # [(path, task_id)]
        self._task_id = 0
        self._cancelled = set()
        self._cache = bbox_cache
        # 队列互斥 + 到达通知 + 退出请求 + 已启动标志（只 start 一次）
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._exit = False
        self._started = False

    def set_cache(self, cache):
        self._cache = cache

    def submit(self, path):
        """提交高优先级任务（用户切换），插到队首"""
        tid = self._task_id
        self._task_id += 1
        self._mutex.lock()
        self._tasks.insert(0, (path, tid))
        need_start = not self._started
        if need_start:
            self._started = True
        self._cond.wakeOne()
        self._mutex.unlock()
        if need_start:
            self.start()
        return tid

    def submit_many(self, paths):
        """批量提交低优先级任务（预扫描），插到队尾"""
        tids = []
        self._mutex.lock()
        for p in paths:
            tid = self._task_id
            self._task_id += 1
            self._tasks.append((p, tid))
            tids.append(tid)
        need_start = not self._started
        if need_start:
            self._started = True
        self._cond.wakeAll()
        self._mutex.unlock()
        if need_start:
            self.start()
        return tids

    def cancel(self, task_id):
        self._mutex.lock()
        self._cancelled.add(task_id)
        self._mutex.unlock()

    def cancel_all(self):
        self._mutex.lock()
        self._cancelled.update(tid for _, tid in self._tasks)
        self._mutex.unlock()

    def pending_count(self):
        self._mutex.lock()
        n = len(self._tasks)
        self._mutex.unlock()
        return n

    def request_stop(self):
        """请求线程退出（唯一退出路径）。调用方负责随后 wait() 收敛。

        同时清空未处理任务：关闭语义下 prescan 的剩余队列不需要跑完，
        wait() 只需等当前一张处理完（否则长队列下 wait 必然超时，
        线程比窗口活得还久）。
        """
        self._mutex.lock()
        self._exit = True
        self._tasks.clear()
        self._cond.wakeOne()
        self._mutex.unlock()

    def run(self):
        # 每轮循环边界持锁：while 条件、pop、取消检查都在锁内；
        # 只在 _process / emit / save（不触碰共享状态）时放锁。
        self._mutex.lock()
        while True:
            while not self._tasks and not self._exit:
                self._cond.wait(self._mutex)
            if self._exit:
                self._mutex.unlock()
                return
            path, tid = self._tasks.pop(0)
            if tid in self._cancelled:
                self._cancelled.discard(tid)
                continue
            self._mutex.unlock()
            try:
                result = self._process(path)
            except Exception as e:
                logger.warning(f"[BboxScanner] 处理失败 {path}: {e}")
                result = None
            # 处理期间可能被取消：取消的任务不发信号
            self._mutex.lock()
            if tid in self._cancelled:
                self._cancelled.discard(tid)
                continue
            self._mutex.unlock()
            self.scan_done.emit(path, result)
            # 每处理完一张保存一次缓存
            if self._cache:
                try:
                    self._cache.save()
                except Exception as e:
                    logger.warning(f"[BboxScanner] 缓存保存失败: {e}")
            self._mutex.lock()

    def _process(self, path):
        """处理单张图：有缓存 bbox 则跳过扫描，无则扫描并写缓存"""
        p = Path(path)
        if not p.exists():
            return None
        try:
            mtime = p.stat().st_mtime_ns
        except OSError:
            mtime = 0

        # 查预扫描缓存
        if self._cache:
            cached_bbox = self._cache.get(path, mtime)
            if cached_bbox is not None:
                return load_with_bbox(path, cached_bbox)

        # 无缓存：扫描 + 裁剪
        scan_result = load_and_crop(path)
        if scan_result is None:
            return None
        result, bbox = scan_result
        # 写回缓存
        if self._cache and bbox is not None:
            self._cache.set(path, bbox, mtime, (result.orig_w, result.orig_h))
        return result

