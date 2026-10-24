"""契约：.gsv 导入的失败路径（S3a / S3b）。

历史 bug ①（S3a）：图片复制失败的 except 块引用未绑定的 `copied`——
NameError 吞掉原始异常，已复制的图片成孤儿留在 resources 里。
历史 bug ②（S3b）：manifest 的图片条目没有路径校验——含 `../` 的恶意 .gsv
可借导入把文件写到 resources 目录之外（任意文件写）。
"""
import json
import shutil
import zipfile

import pytest

from core.vehicle_io import FORMAT_VERSION, import_vehicle


def _make_gsv(path, images, files=None, name="T"):
    """构造一个 .gsv：manifest.json + images/ 下的文件。"""
    files = files or {}
    with zipfile.ZipFile(path, "w") as zf:
        manifest = {
            "format_version": FORMAT_VERSION,
            "vehicle": {"name": name},
            "images": images,
        }
        zf.writestr("manifest.json", json.dumps(manifest))
        for rel, content in files.items():
            zf.writestr(rel, content)


@pytest.mark.parametrize("bad_entry", [
    "../escape/x.png",       # 目录穿越
    "sub/../../x.png",       # 嵌套穿越
    "C:/Windows/evil.png",   # 绝对路径（pathlib 拼接会整体替换 base）
])
def test_import_rejects_path_traversal(config, tmp_path, bad_entry):
    """S3b：manifest 图片条目越出 resources → 拒绝且不在磁盘留痕。"""
    resources = tmp_path / "resources"
    resources.mkdir()
    gsv = tmp_path / "evil.gsv"
    _make_gsv(gsv, images=[bad_entry])

    ok, msg, _new_name = import_vehicle(config, resources, gsv)

    assert ok is False
    assert "非法" in msg
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "x.png").exists()
    assert config._config["vehicles"] == {}


def test_import_image_failure_reports_original_error(config, tmp_path, monkeypatch):
    """S3a：复制中途失败 → 报原始异常并清理已复制文件（不是 NameError）。"""
    import core.vehicle_io as vio

    resources = tmp_path / "resources"
    resources.mkdir()
    gsv = tmp_path / "flaky.gsv"
    _make_gsv(gsv, images=["sub/a.png", "sub/b.png"],
              files={"images/sub/a.png": "A", "images/sub/b.png": "B"})

    real_copy2 = shutil.copy2
    state = {"n": 0}

    def flaky(src, dst):
        state["n"] += 1
        if state["n"] > 1:
            raise OSError("disk full")
        return real_copy2(src, dst)

    monkeypatch.setattr(vio.shutil, "copy2", flaky)

    ok, msg, _new_name = import_vehicle(config, resources, gsv)

    assert ok is False
    assert "disk full" in msg  # 修复前这里抛 NameError: copied
    assert not (resources / "sub" / "a.png").exists()  # 孤儿被清理


def test_import_normal_flow_still_works(config, tmp_path):
    """对照：正常导入不受路径校验影响（防过度收紧）。"""
    resources = tmp_path / "resources"
    resources.mkdir()
    gsv = tmp_path / "ok.gsv"
    _make_gsv(gsv, images=["sub/a.png"], files={"images/sub/a.png": "A"})

    ok, _msg, new_name = import_vehicle(config, resources, gsv)

    assert ok is True
    assert (resources / "sub" / "a.png").exists()
    assert new_name in config._config["vehicles"]
