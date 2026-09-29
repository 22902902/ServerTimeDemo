"""把**历史遗留**的流程截图收进统一目录 —— 纯逻辑 + 一个可替换的搬运动作。

为什么需要这一步
------------------------------------------------------------------------------
早期截图是直接丢在 ``account_images/`` 根目录的，库里还存着 Windows 反斜杠
``account_images\\20260707_153800.png``。规范目录后来改成
``account_images/process_flows/<流程 id>/``。两套写法混着的后果是：

* **孤儿回收认不出来**：``collect_orphan_screenshots`` 按字符串比对路径，
  ``a\\b.png`` 与 ``a/b.png`` 是两条 —— 该回收的收不回，甚至可能误删；
* 几百张图平铺在一个目录里，想找某个流程的截图只能靠库反查。

所以迁移做两件事：把文件搬进 ``process_flows/<flow_id>/``，把库里的路径统一成
**相对 BASE_DIR 的正斜杠**。

三条硬约束：
* **幂等**：已经规范的那些原样不动，跑多少次结果都一样；
* **源不在就别动库**：文件没了而把路径改掉，等于把引用也一起丢了；
* **搬运失败不拦启动**：这只是一次整理，不该因为它开不了程序。
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["SUBDIR_ROOT", "plan_step", "migrate", "normalize_rel"]

SUBDIR_ROOT = "process_flows"


def normalize_rel(text: str) -> str:
    """统一成正斜杠（库里存的是相对 BASE_DIR 的路径）。"""
    return str(text or "").strip().replace("\\", "/")


def _split(value) -> list[str]:
    """拆 ``screenshot_path``：JSON 数组 / `` | `` / 换行 / 单路径。"""
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, list):
            out = []
            for item in data:
                if isinstance(item, dict):
                    path = (item.get("path") or item.get("image_path")
                            or item.get("value"))
                else:
                    path = item
                path = normalize_rel(path)
                if path:
                    out.append(path)
            return list(dict.fromkeys(out))
    if " | " in text:
        parts = text.split(" | ")
    elif "\n" in text:
        parts = text.splitlines()
    else:
        parts = [text]
    cleaned = [normalize_rel(p) for p in parts]
    return list(dict.fromkeys(p for p in cleaned if p))


def _join(paths: list[str]) -> str:
    """按原约定回写：一张图是裸字符串，多张才是 JSON 数组。"""
    if not paths:
        return ""
    if len(paths) == 1:
        return paths[0]
    return json.dumps(paths, ensure_ascii=False)


def _target_rel(source_rel: str, flow_id) -> str:
    """目标相对路径：``account_images/process_flows/<flow_id>/<文件名>``。"""
    name = source_rel.rsplit("/", 1)[-1] or "screenshot.png"
    return f"account_images/{SUBDIR_ROOT}/{int(flow_id)}/{name}"


def plan_step(value, flow_id) -> tuple[str, list[tuple[str, str]]]:
    """给一条 ``screenshot_path`` 出方案：**不改任何东西**。

    返回 ``(新值, [(源相对路径, 目标相对路径)])``。已经在规范目录里的原样不动
    —— 这是幂等的根本。
    """
    paths = _split(value)
    if not paths:
        return (str(value or ""), [])

    planned: list[str] = []
    moves: list[tuple[str, str]] = []
    for path in paths:
        norm = normalize_rel(path)
        parts = norm.split("/")
        # 已经在规范目录下（account_images/process_flows/...）就不用动
        if (len(parts) >= 3 and parts[0] == "account_images"
                and parts[1] == SUBDIR_ROOT):
            planned.append(norm)
            continue
        # 老数据里还有直接写绝对路径、或放在别的目录下的 —— 能找到就照样收编
        target = _target_rel(norm, flow_id)
        moves.append((norm, target))
        planned.append(target)
    return (_join(planned), moves)


def migrate(db, base_dir, *, move=None, exists=None) -> dict:
    """搬文件 + 回写路径。**幂等**：已经规范的不会再来一遍。

    ``move`` 可注入（测试里换成记录器就完全不碰磁盘）；``exists`` 同理。
    返回 ``{"moved", "missing", "steps", "unchanged"}``。
    """
    root = Path(base_dir)
    if move is None:
        import shutil

        def move(src, dst):                     # noqa: F811  （默认实现）
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
    if exists is None:
        exists = lambda path: Path(path).exists()   # noqa: E731

    stats = {"moved": 0, "missing": 0, "steps": 0, "unchanged": 0}
    # 逐流程取步骤：数据层没有「全库步骤」的入口，而流程本来就得遍历一遍
    try:
        flows = db.fetch_process_flows()
    except Exception:                            # noqa: BLE001
        return stats
    rows = []
    for flow in flows:
        try:
            steps = db.fetch_process_steps(flow["id"])
        except Exception:                        # noqa: BLE001
            continue
        keys = steps[0].keys() if steps else ()
        for step in steps:
            # sqlite3.Row 没有 .get()（连 fetch_process_steps 返回的就是它）
            value = step["screenshot_path"] if "screenshot_path" in keys else ""
            rows.append({"id": step["id"], "flow_id": flow["id"],
                         "screenshot_path": value or ""})

    for row in rows:
        step_id = row["id"]
        flow_id = row.get("flow_id")
        raw = row.get("screenshot_path") or ""
        new_value, moves = plan_step(raw, flow_id)
        if new_value == str(raw):
            stats["unchanged"] += 1
            continue
        if not moves:                            # 只是分隔符 / 斜杠不同
            try:
                db.update_process_step_screenshot(step_id, new_value)
                stats["steps"] += 1
            except Exception:                    # noqa: BLE001
                pass
            continue

        done = 0
        for source_rel, target_rel in moves:
            source = root / source_rel
            if not source.is_absolute():
                source = root / source_rel
            if not exists(source):
                stats["missing"] += 1
                continue
            target = root / target_rel
            if exists(target) and str(source) != str(target):
                # 目标已有同名文件：加个后缀，绝不覆盖（覆盖就是丢图）
                stem, suffix = target.stem, target.suffix
                index = 2
                while exists(target.with_name(f"{stem}_{index}{suffix}")):
                    index += 1
                target = target.with_name(f"{stem}_{index}{suffix}")
                target_rel = str(
                    target.relative_to(root)).replace("\\", "/")
                new_value = new_value.replace(
                    _target_rel(source_rel, flow_id), target_rel)
            try:
                move(source, target)
                done += 1
                stats["moved"] += 1
            except Exception:                    # noqa: BLE001
                stats["missing"] += 1
        if done:
            try:
                db.update_process_step_screenshot(step_id, new_value)
                stats["steps"] += 1
            except Exception:                    # noqa: BLE001
                pass
        else:
            stats["unchanged"] += 1
    return stats
