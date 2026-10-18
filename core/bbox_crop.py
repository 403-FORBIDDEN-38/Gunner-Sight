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
"""
import json
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage

from core.logger import logger


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
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._data = {}
            self._path.unlink(missing_ok=True)

    def cleanup(self):
        """删除文件不存在或 mtime 不匹配的孤儿条目"""
        removed = 0
        for rel in list(self._data.keys()):
            p = Path(self._to_abs(rel))
            if not p.exists():
                del self._data[rel]
                removed += 1
                continue
            try:
                mtime = p.stat().st_mtime_ns
            except OSError:
                del self._data[rel]
                removed += 1
                continue
            if self._data[rel].get("mtime") != mtime:
                del self._data[rel]
                removed += 1
        if removed > 0:
            self._dirty = True
            self.save()

    def save(self):
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
        """查询缓存，命中且 mtime 匹配返回 bbox tuple，否则 None。结构异常的条目自动清除。"""
        rel = self._to_rel(path)
        entry = self._data.get(rel)
        if not isinstance(entry, dict):
            if entry is not None:
                del self._data[rel]
                self._dirty = True
            return None
        if entry.get("mtime") == mtime and isinstance(entry.get("bbox"), list) and len(entry["bbox"]) == 4:
            return tuple(entry["bbox"])
        return None

    def set(self, path, bbox, mtime, orig_size):
        """写入缓存"""
        rel = self._to_rel(path)
        self._data[rel] = {
            "bbox": list(bbox),
            "mtime": mtime,
            "orig_size": list(orig_size),
        }
        self._dirty = True

    def has(self, path, mtime):
        return self.get(path, mtime) is not None

    def all_paths(self):
        return [self._to_abs(rel) for rel in self._data]


class BboxScanner(QThread):
    """
    后台扫描 bbox 的 QThread。
    - 单线程串行扫描
    - 支持按 task_id 取消
    - 支持预计算 bbox（跳过扫描）
    - 扫描完发 scan_done 信号，自动写回 BboxCache
    """
    scan_done = pyqtSignal(str, object)  # path, CropResult（或 None）

    def __init__(self, bbox_cache=None, parent=None):
        super().__init__(parent)
        self._tasks = []  # [(path, task_id)]
        self._task_id = 0
        self._cancelled = set()
        self._cache = bbox_cache

    def set_cache(self, cache):
        self._cache = cache

    def submit(self, path):
        """提交高优先级任务（用户切换），插到队首"""
        tid = self._task_id
        self._task_id += 1
        self._tasks.insert(0, (path, tid))
        if not self.isRunning():
            self.start()
        return tid

    def submit_many(self, paths):
        """批量提交低优先级任务（预扫描），插到队尾"""
        tids = []
        for p in paths:
            tid = self._task_id
            self._task_id += 1
            self._tasks.append((p, tid))
            tids.append(tid)
        if not self.isRunning():
            self.start()
        return tids

    def cancel(self, task_id):
        self._cancelled.add(task_id)

    def cancel_all(self):
        self._cancelled.update(tid for _, tid in self._tasks)

    def pending_count(self):
        return len(self._tasks)

    def run(self):
        while self._tasks:
            path, tid = self._tasks.pop(0)
            if tid in self._cancelled:
                self._cancelled.discard(tid)
                continue
            try:
                result = self._process(path)
            except Exception as e:
                logger.warning(f"[BboxScanner] 处理失败 {path}: {e}")
                result = None
            if tid in self._cancelled:
                self._cancelled.discard(tid)
                continue
            self.scan_done.emit(path, result)
            # 每处理完一张保存一次缓存
            if self._cache:
                try:
                    self._cache.save()
                except Exception as e:
                    logger.warning(f"[BboxScanner] 缓存保存失败: {e}")

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

