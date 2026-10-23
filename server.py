#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ColorOS 17 主题工坊 —— 本地服务

    python server.py                启动并打开浏览器(默认 127.0.0.1:8765)
    python server.py --port 8899    指定端口
    python server.py --no-open      不自动开浏览器

只依赖 Python 标准库 + Pillow。
"""

from __future__ import annotations

import argparse
import base64
import colorsys
import hashlib
import io
import json
import os
import re
import socket
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from PIL import Image  # noqa: E402

from themelib.core import (  # noqa: E402
    BuildOptions,
    Theme,
    image_size,
    new_uuid,
)

TPL_DIR = os.path.join(BASE, "templates")
OUT_DIR = os.path.join(BASE, "output")
WORK_DIR = os.path.join(BASE, "work")
UP_DIR = os.path.join(WORK_DIR, "uploads")
THUMB_DIR = os.path.join(WORK_DIR, "thumbs")
WEB_DIR = os.path.join(BASE, "web")

for _d in (TPL_DIR, OUT_DIR, UP_DIR, THUMB_DIR):
    os.makedirs(_d, exist_ok=True)

LOCK = threading.Lock()
THEME_CACHE: dict[str, Theme] = {}
ASSET_CACHE: dict[str, bytes] = {}


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def tpl_id(path: str) -> str:
    return hashlib.md5(os.path.abspath(path).encode("utf-8")).hexdigest()[:10]


def find_template(tid: str) -> str | None:
    for fn in os.listdir(TPL_DIR):
        p = os.path.join(TPL_DIR, fn)
        if fn.lower().endswith(".theme") and tpl_id(p) == tid:
            return p
    return None


def get_theme(tid: str, reload: bool = False) -> Theme:
    with LOCK:
        if not reload and tid in THEME_CACHE:
            return THEME_CACHE[tid]
    path = find_template(tid)
    if not path:
        raise FileNotFoundError("模板不存在,请重新选择")
    t = Theme(path).load()
    with LOCK:
        THEME_CACHE[tid] = t
    return t


def safe_name(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", s or "").strip()
    return s[:60] or "theme"


def thumb_bytes(data: bytes, width: int = 300) -> bytes:
    im = Image.open(io.BytesIO(data))
    im = im.convert("RGBA")
    if width and im.width > width:
        im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


def dominant_color(data: bytes) -> str:
    """取图片主色调(量化色相桶 + 忽略灰/黑/白)"""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((96, 96))
    px = im.load()
    buckets: dict[tuple, int] = {}
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = px[x, y]
            h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            if s < 0.18 or l < 0.15 or l > 0.90:
                continue
            key = (round(h * 24), round(s * 6), round(l * 6))
            buckets[key] = buckets.get(key, 0) + 1
    if not buckets:
        return "#FF42D4E4"
    best = max(buckets.items(), key=lambda kv: kv[1])[0]
    h = best[0] / 24.0
    s = min(1.0, (best[1] + 0.6) / 6)
    l = min(0.85, max(0.30, (best[2] + 0.5) / 6))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#FF%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def decode_data_url(s: str) -> bytes:
    s = s.strip()
    if s.lower().startswith("data:") and "," in s:
        s = s.split(",", 1)[1]
    return base64.b64decode(s)


def load_upload(uid: str | None) -> bytes | None:
    if not uid:
        return None
    p = os.path.join(UP_DIR, os.path.basename(uid))
    return open(p, "rb").read() if os.path.exists(p) else None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def api_templates() -> dict:
    items = []
    for fn in sorted(os.listdir(TPL_DIR)):
        p = os.path.join(TPL_DIR, fn)
        if not fn.lower().endswith(".theme"):
            continue
        tid = tpl_id(p)
        meta = {
            "id": tid, "file": fn, "size": os.path.getsize(p),
            "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p))),
        }
        try:
            t = get_theme(tid)
            meta["info"] = {
                "summary": t.info.summary, "author": t.info.author,
                "description": t.info.description, "uuid": t.info.uuid,
            }
            meta["packages"] = len(t.packages)
            prev = t.preview_images()
            menu = next((x for x in prev if x["key"] == "menu"), prev[0] if prev else None)
            meta["cover"] = (f"/asset?tpl={tid}&path={urllib.parse.quote(menu['path'])}&w=420"
                             if menu else None)
        except Exception as e:  # noqa: BLE001
            meta["error"] = str(e)
            meta["info"] = {"summary": fn, "author": ""}
        items.append(meta)
    return {"templates": items}


def api_template_load(body: dict) -> dict:
    tid = body["id"]
    t = get_theme(tid, reload=bool(body.get("reload")))
    stats = t.color_stats()

    def url(pkg: str, path: str, w: int) -> str:
        q = f"tpl={tid}&path={urllib.parse.quote(path)}&w={w}"
        if pkg:
            q += f"&pkg={urllib.parse.quote(pkg)}"
        return "/asset?" + q

    previews = []
    for p in t.preview_images():
        raw = next((e.data for e in t.entries if e.name == p["path"]), b"")
        pw, ph = image_size(raw)
        previews.append({**p, "w": pw, "h": ph, "url": url("", p["path"], 560)})

    # 预览要用的几个关键资源(设置背景、音量面板、关于本机)
    key_assets = {}
    # C16 用的是 systemui_icon_volume_bg，统一映射到同一个槽位
    VOLUME_NAMES = ("systemui_panel_volume_bg.9.png", "systemui_icon_volume_bg.9.png")
    for a in t.asset_list():
        if a["file"] in VOLUME_NAMES:
            key_assets.setdefault("systemui_panel_volume_bg.9.png",
                                  url(a["pkg"], a["path"], 760))
        if a["file"] in ("coui_window_background_selector.9.png",
                         "coui_window_background_with_card_selector.9.png",
                         "systemui_panel_volume_bg.9.png",
                         "pb_bg_dialer.9.png",
                         "about_device_top_video_last_frame_17.png"):
            key_assets.setdefault(a["file"], url(a["pkg"], a["path"], 760))

    return {
        "id": tid,
        "info": {
            "summary": t.info.summary, "author": t.info.author,
            "description": t.info.description, "uuid": t.info.uuid,
            "version_name": t.info.version_name, "version_code": t.info.version_code,
            "is_global": t.info.is_global,
        },
        "packages": t.package_summary(),
        "palette": stats,
        "wallpapers": [{**w, "url": url(w["pkg"], w["path"], 300)} for w in t.wallpapers()],
        "icons": [{**i, "url": url("icons", i["path"], 160)} for i in t.icon_list()],
        "previews": previews,
        "key_assets": key_assets,
    }


def api_assets(tid: str) -> dict:
    t = get_theme(tid)
    # 图标和壁纸已有专门入口,这里不再重复列出
    rows = [r for r in t.asset_list() if r["base"] not in ("icons", "wallpaper")]

    def url(r: dict, w: int = 120) -> str:
        return (f"/asset?tpl={tid}&pkg={urllib.parse.quote(r['pkg'])}"
                f"&path={urllib.parse.quote(r['path'])}&w={w}")

    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["base"], []).append({**r, "url": url(r)})
    return {
        "total": len(rows),
        "packages": [
            {"base": k, "count": len(v),
             "nine": sum(1 for x in v if x["nine"]),
             "kb": sum(x["kb"] for x in v)}
            for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))
        ],
        "assets": [{**r, "url": url(r)} for r in rows],
    }


def build_options_from(body: dict) -> BuildOptions:
    o = BuildOptions(
        name=body.get("name") or "我的主题",
        author=body.get("author") or "",
        description=body.get("description") or "",
        uuid=(body.get("uuid") or "").strip(),
        version_name=body.get("version_name") or "1.0.0",
        version_code=int(body.get("version_code") or 1),
        primary=body.get("primary") or "#FF42D4E4",
        anchor=body.get("anchor") or "",
        strength=float(body.get("strength", 1.0)),
        hue_only=bool(body.get("hue_only")),
        protect_neutrals=bool(body.get("protect_neutrals", True)),
        tint_light=bool(body.get("tint_light")),
        recolor=bool(body.get("recolor", True)),
        color_overrides=body.get("overrides") or {},
        icon_shape=body.get("icon_shape") or "",
        icon_scale=float(body.get("icon_scale") or 0),
        tint_systemui=bool(body.get("tint_systemui")),
        tint_color=body.get("tint_color") or body.get("primary") or "",
        icon_packages=body.get("icon_packages") or {},
        wallpaper_fit=body.get("wallpaper_fit") or "cover",
        asset_fit=body.get("asset_fit") or "cover",
        asset_compress=bool(body.get("asset_compress", True)),
        is_global=bool(body.get("is_global", True)),
    )
    if not re.fullmatch(r"[0-9A-Fa-f]{32}", o.uuid or ""):
        o.uuid = new_uuid()

    if body.get("wallpaper"):
        o.wallpaper = load_upload(body["wallpaper"])
    if body.get("lockscreen"):
        o.lockscreen = load_upload(body["lockscreen"])

    for item in body.get("icons") or []:
        if isinstance(item, dict):
            blob = load_upload(item.get("upload"))
            if blob:
                o.icons[item.get("name") or item["upload"]] = blob
    o.icon_remove = [x for x in (body.get("icon_remove") or []) if isinstance(x, str)]
    for item in body.get("assets") or []:
        blob = load_upload(item.get("upload"))
        if blob and item.get("file"):
            o.assets.append({
                "file": item["file"],
                "pkg": item.get("pkg") or "",
                "sync": bool(item.get("sync", True)),
                "fit": item.get("fit") or "",
                "data": blob,
            })
    for key, uid in (body.get("previews") or {}).items():
        blob = load_upload(uid)
        if blob:
            o.previews[key] = blob
    for item in body.get("preview_add") or []:
        blob = load_upload(item.get("upload"))
        if blob:
            o.preview_add.append({"name": item.get("name") or "preview_extra.png", "data": blob})
    o.preview_remove = [x for x in (body.get("preview_remove") or []) if isinstance(x, str)]
    return o


def api_palette(body: dict) -> dict:
    t = get_theme(body["tpl"])
    opts = build_options_from(body)
    tr = opts.color_transform()
    overrides = {k.upper(): v for k, v in (body.get("overrides") or {}).items()}
    out = []
    for s in t.color_stats()["swatches"]:
        key = s["hex"].upper()
        # 用户手动指定了该原色的目标色 -> 直接用，不再跑算法
        if key in overrides and overrides[key]:
            out.append({**s, "out": "#" + overrides[key].lstrip("#").upper()[:6],
                        "custom": True})
            continue
        out.append({**s, "out": (tr.sample(s["hex"]) if tr else s["rgb"])})
    return {"swatches": out, "transform": None if tr is None else {
        "hue": round(tr._d_h * 360, 1), "sat": round(tr._s_ratio, 2)}}


def save_upload(name: str, data: bytes) -> dict:
    """落盘一张上传图片,返回元信息"""
    name = name or "image.png"
    ext = os.path.splitext(name)[1].lower() or ".png"
    uid = hashlib.md5(data).hexdigest()[:12] + ext
    path = os.path.join(UP_DIR, uid)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
    try:
        im = Image.open(io.BytesIO(data))
        w, h = im.size
    except Exception:  # noqa: BLE001
        w = h = 0
    return {"id": uid, "name": name, "w": w, "h": h, "size": len(data),
            "url": "/upload/" + uid}


def api_upload(body: dict) -> dict:
    res = save_upload(body.get("name") or "image.png", decode_data_url(body["data"]))
    if body.get("dominant"):
        try:
            res["dominant"] = dominant_color(decode_data_url(body["data"]))
        except Exception:  # noqa: BLE001
            pass
    return res


def api_upload_batch(body: dict) -> dict:
    """批量上传(图标一次导入几十上百个)"""
    out = []
    for item in body.get("items") or []:
        try:
            out.append(save_upload(item.get("name") or "image.png",
                                   decode_data_url(item["data"])))
        except Exception as exc:  # noqa: BLE001
            out.append({"name": item.get("name"), "error": str(exc)})
    return {"items": out}


def api_build(body: dict) -> dict:
    t0 = time.time()
    t = get_theme(body["tpl"])
    opts = build_options_from(body)
    fname = f"{safe_name(opts.name)}_{time.strftime('%m%d-%H%M%S')}.theme"
    out = os.path.join(OUT_DIR, fname)
    res = t.build(opts, out)
    res.update({
        "ok": True,
        "filename": fname,
        "download": "/download/" + urllib.parse.quote(fname),
        "elapsed": round(time.time() - t0, 2),
    })
    return res


def api_template_upload(body: dict) -> dict:
    data = decode_data_url(body["data"])
    name = safe_name(body.get("name") or "imported")
    if not name.lower().endswith(".theme"):
        name += ".theme"
    path = os.path.join(TPL_DIR, name)
    with open(path, "wb") as f:
        f.write(data)
    t = Theme(path).load()  # 立即校验,失败会抛异常
    return {"id": tpl_id(path), "file": name, "packages": len(t.packages),
            "summary": t.info.summary}


def api_delete_template(body: dict) -> dict:
    p = find_template(body["id"])
    if p:
        with LOCK:
            THEME_CACHE.pop(body["id"], None)
        os.remove(p)
    return {"ok": True}


def api_outputs() -> dict:
    items = []
    for fn in sorted(os.listdir(OUT_DIR), reverse=True):
        p = os.path.join(OUT_DIR, fn)
        if fn.endswith(".theme"):
            items.append({"file": fn, "size": os.path.getsize(p),
                          "time": time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(p))),
                          "download": "/download/" + urllib.parse.quote(fn)})
    return {"outputs": items[:30]}


# ---------------------------------------------------------------------------
# 资源
# ---------------------------------------------------------------------------

def resolve_asset(q: dict) -> tuple[bytes, str]:
    tid = q.get("tpl", [""])[0]
    path = q.get("path", [""])[0]
    pkg_name = q.get("pkg", [""])[0]
    width = int(q.get("w", ["0"])[0] or 0)
    t = get_theme(tid)

    key = f"{tid}|{pkg_name}|{path}|{width}"
    if key in ASSET_CACHE:
        return ASSET_CACHE[key], "image/png"

    data = None
    if pkg_name:
        pkg = t.packages.get(pkg_name)
        if pkg:
            data = pkg.read(path)
    if data is None:
        for e in t.entries:
            if e.name == path:
                data = e.data
                break
    if data is None:
        raise FileNotFoundError(path)

    if width:
        data = thumb_bytes(data, width)
        mime = "image/png"
    else:
        mime = "image/jpeg" if path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    if len(data) < 3 * 1024 * 1024:
        ASSET_CACHE[key] = data
    return data, mime


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "ThemeStudio/1.0"

    def log_message(self, fmt, *args):  # 安静一点
        if "--verbose" in sys.argv:
            super().log_message(fmt, *args)

    # -- 基础 --------------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str = "application/json",
              extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if ctype == "application/json" else "max-age=600")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _err(self, msg: str, code: int = 400):
        self._json({"ok": False, "error": msg}, code)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        raw = self.rfile.read(n)
        return json.loads(raw.decode("utf-8"))

    # -- 路由 --------------------------------------------------------------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        p = urllib.parse.unquote(u.path)
        try:
            if p in ("/", "/index.html"):
                return self._file(os.path.join(WEB_DIR, "index.html"))
            if p.startswith("/static/"):
                return self._file(os.path.join(WEB_DIR, p[len("/static/"):]))
            if p.startswith("/upload/"):
                fp = os.path.join(UP_DIR, os.path.basename(p[len("/upload/"):]))
                return self._file(fp)
            if p.startswith("/download/"):
                fp = os.path.join(OUT_DIR, os.path.basename(p[len("/download/"):]))
                return self._file(fp, download=True)
            if p == "/asset":
                data, mime = resolve_asset(q)
                return self._send(200, data, mime)
            if p == "/api/templates":
                return self._json(api_templates())
            if p == "/api/assets":
                return self._json(api_assets(q.get("tpl", [""])[0]))
            if p == "/api/outputs":
                return self._json(api_outputs())
            if p == "/api/ping":
                return self._json({"ok": True, "version": "1.0"})
            return self._err("not found", 404)
        except FileNotFoundError as e:
            return self._err(f"资源不存在: {e}", 404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._err(str(e), 500)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            body = self._body()
            routes = {
                "/api/template/load": api_template_load,
                "/api/template/upload": api_template_upload,
                "/api/template/delete": api_delete_template,
                "/api/upload": api_upload,
                "/api/upload_batch": api_upload_batch,
                "/api/palette": api_palette,
                "/api/build": api_build,
            }
            fn = routes.get(u.path)
            if not fn:
                return self._err("not found", 404)
            return self._json(fn(body))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._err(str(e), 500)

    def _file(self, path: str, download: bool = False):
        if not os.path.isfile(path):
            return self._err("not found", 404)
        ctype = mimetypes_guess(path)
        data = open(path, "rb").read()
        extra = {}
        if download:
            fn = urllib.parse.quote(os.path.basename(path))
            extra["Content-Disposition"] = f"attachment; filename*=UTF-8''{fn}"
            ctype = "application/octet-stream"
        self._send(200, data, ctype, extra)


def mimetypes_guess(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".theme": "application/octet-stream",
    }.get(ext, "application/octet-stream")


def main():
    ap = argparse.ArgumentParser(description="ColorOS 17 主题工坊")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    url = f"http://127.0.0.1:{args.port}/"

    # 已经有一个实例在跑:直接打开浏览器,不重复启动
    if port_alive(args.port):
        print(f"工坊已经在运行: {url}")
        if not args.no_open:
            webbrowser.open(url)
        raise SystemExit(3)

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("=" * 56)
    print("  ColorOS 17 主题工坊")
    print(f"  模板目录: {TPL_DIR}")
    print(f"  输出目录: {OUT_DIR}")
    print(f"  访问地址: {url}")
    print("  按 Ctrl+C 停止")
    print("=" * 56)
    if not args.no_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        srv.shutdown()


def port_alive(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


if __name__ == "__main__":
    main()
