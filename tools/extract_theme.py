#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ColorOS 主题解析导出器

把一个 .theme 完整拆开:
  - 导出所有子包内容到 packages/<包名>/原路径
  - 导出顶层文件到根目录
  - 生成 manifest.json(结构化清单)
  - 生成 report.html(可浏览的资源报告,带缩略图、尺寸、配色表)

用法:
    python tools/extract_theme.py "D:/path/主题.theme"
    python tools/extract_theme.py "主题.theme" --out exports/自定义名字
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import os
import re
import shutil
import sys
import zipfile
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from themelib.core import Theme, image_size, parse_hex, rgb_to_hls  # noqa: E402

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

def safe_dirname(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "theme"


def extract(theme_path: str, out_dir: str) -> dict:
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    t = Theme(theme_path).load()
    root = os.path.dirname(os.path.abspath(theme_path))

    # 顶层文件(themeInfo.xml、picture/... 等非子包条目)
    top_files = []
    for e in t.entries:
        if e.name.endswith("/"):
            continue
        pkg = t.packages.get(e.name)
        if pkg is not None:
            continue
        dst = os.path.join(out_dir, e.name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(e.data)
        top_files.append({
            "path": e.name,
            "size": len(e.data),
            "w": image_size(e.data)[0],
            "h": image_size(e.data)[1],
        })

    # 子包
    packages = []
    total_images = 0
    total_image_bytes = 0
    formats = Counter()

    # 先从原文件里拿原始压缩信息(导出用原字节,保证无损)
    with zipfile.ZipFile(theme_path) as z:
        raw = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}

    for pkg_name, pkg in t.packages.items():
        base_dir = os.path.join(out_dir, "packages", safe_dirname(pkg_name))
        files = []
        outer = zipfile.ZipFile(io.BytesIO(raw[pkg_name]))
        for item in outer.infolist():
            if item.is_dir():
                continue
            data = outer.read(item.filename)
            dst = os.path.join(base_dir, item.filename)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)

            low = item.filename.lower()
            is_img = low.endswith(IMG_EXT)
            rec = {
                "path": item.filename,
                "size": len(data),
                "kind": "image" if is_img else ("xml" if low.endswith(".xml") else "other"),
            }
            if is_img:
                w, h = image_size(data)
                rec["w"], rec["h"] = w, h
                rec["nine"] = low.endswith(".9.png")
                rec["ext"] = os.path.splitext(low)[1]
                formats[rec["ext"]] += 1
                total_images += 1
                total_image_bytes += len(data)
            files.append(rec)

        colors = []
        for fpath, entries in pkg.colorfiles.items():
            for ce in entries:
                p = parse_hex(ce.value)
                if not p:
                    continue
                h, l, s = rgb_to_hls(*p[1:])
                colors.append({
                    "name": ce.name,
                    "value": ce.value.upper(),
                    "rgb": "#%02X%02X%02X" % p[1:],
                    "a": p[0],
                    "h": round(h * 360),
                    "l": round(l * 100),
                    "s": round(s * 100),
                })

        packages.append({
            "name": pkg_name,
            "base": pkg.base_name,
            "version": pkg.version,
            "dir": f"packages/{safe_dirname(pkg_name)}",
            "files": files,
            "colors": colors,
            "images": sum(1 for f in files if f["kind"] == "image"),
            "bytes": sum(f["size"] for f in files),
        })

    packages.sort(key=lambda p: (-p["images"], p["name"]))

    manifest = {
        "source": os.path.abspath(theme_path),
        "file_size": os.path.getsize(theme_path),
        "info": {
            "summary": t.info.summary, "author": t.info.author,
            "description": t.info.description, "uuid": t.info.uuid,
            "editor_version": t.info.editor_version,
            "version_name": t.info.version_name, "version_code": t.info.version_code,
            "is_global": t.info.is_global, "last_modify": t.info.last_modify,
            "declared_packages": t.info.extra_packages,
        },
        "stats": {
            "packages": len(packages),
            "images": total_images,
            "image_bytes": total_image_bytes,
            "formats": dict(formats),
            "colors": sum(len(p["colors"]) for p in packages),
            "unique_colors": len({c["value"] for p in packages for c in p["colors"]}),
        },
        "top_files": top_files,
        "packages": packages,
    }

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    with open(os.path.join(out_dir, "report.html"), "w", encoding="utf-8") as f:
        f.write(render_report(manifest, out_dir))

    return manifest


# ---------------------------------------------------------------------------
# 缩略图
# ---------------------------------------------------------------------------

THUMB_CACHE: dict[str, str] = {}


def thumb(path: str, size: int = 150) -> str:
    """缩略图:统一转成深色底 JPEG,体积只有 PNG 的十分之一"""
    key = f"{path}|{size}"
    if key in THUMB_CACHE:
        return THUMB_CACHE[key]
    try:
        im = Image.open(path)
        im.thumbnail((size, size), Image.LANCZOS)
        bg = Image.new("RGB", im.size, (18, 21, 28))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg.paste(im, (0, 0), im.split()[3])
        else:
            bg.paste(im.convert("RGB"), (0, 0))
        buf = io.BytesIO()
        bg.save(buf, "JPEG", quality=74, optimize=True)
        uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        uri = ""
    THUMB_CACHE[key] = uri
    return uri


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

def human(n: float) -> str:
    return f"{n / 1048576:.2f} MB" if n > 1048576 else f"{n / 1024:.0f} KB"


def render_report(m: dict, out_dir: str) -> str:
    info = m["info"]
    st = m["stats"]

    # 配色汇总(同名同值只保留一份)
    color_rows = []
    seen_colors = set()
    for p in m["packages"]:
        for c in p["colors"]:
            key = (c["name"], c["value"])
            if key in seen_colors:
                continue
            seen_colors.add(key)
            color_rows.append((p["base"], c))
    color_rows.sort(key=lambda x: (-x[1]["l"], x[1]["name"]))

    # 图片按目录分组
    sections = []
    for p in m["packages"]:
        imgs = [f for f in p["files"] if f["kind"] == "image"]
        if not imgs:
            continue
        dirs: dict[str, list] = defaultdict(list)
        for f in imgs:
            d = os.path.dirname(f["path"]) or "."
            dirs[d].append(f)
        for d, items in dirs.items():
            items.sort(key=lambda x: x["path"])
            sections.append((p, d, items))

    total_sections = len(sections)
    pkg_html = []
    anchor_of: dict[str, int] = {}
    for si, (p, d, items) in enumerate(sections):
        anchor_of.setdefault(p["base"], si)
        seq = sequence_map(items)
        seq_totals: dict[str, int] = {v[0]: v[2] for v in seq.values()}
        cards = []
        for f in items:
            rel = f"{p['dir']}/{f['path']}"
            full = os.path.join(out_dir, rel)
            sinfo = seq.get(f["path"])
            hidden = ' hidden data-late="1"' if sinfo and sinfo[1] >= 4 else ''
            attr = f' data-seq="{html.escape(sinfo[0])}"' if sinfo else ''
            t = thumb(full, 150 if not sinfo else 82)
            tags = []
            if f.get("nine"):
                tags.append('<i class="tg tg9">.9</i>')
            if f["ext"] == ".webp":
                tags.append('<i class="tg tgw">webp</i>')
            cards.append(f"""      <figure class="card"{attr}{hidden}>
        <a href="{html.escape(rel)}" target="_blank" class="thumb"><img src="{t}" alt=""></a>
        <figcaption>
          <b title="{html.escape(f['path'])}">{html.escape(os.path.basename(f['path']))}</b>
          <small>{f['w']}×{f['h']} · {human(f['size'])}</small>
          {''.join(tags)}
        </figcaption>
      </figure>""")
        extra = "".join(
            f'<button class="more" data-seq="{html.escape(stem)}">展开「{html.escape(stem)}」序列共 {total} 张</button>'
            for stem, total in seq_totals.items())
        pkg_html.append(f"""
    <section class="pkg" id="pkg-{si}">
      <header>
        <h2>{html.escape(p['base'])} <em>{html.escape(p['name'])}</em></h2>
        <div class="meta">{len(items)} 张图 · {human(sum(f['size'] for f in items))}</div>
      </header>
      <div class="dir">{html.escape(d)}</div>
      <div class="grid">
{chr(10).join(cards)}
      </div>
      <div class="more-row">{extra}</div>
    </section>""")

    # 包索引
    idx = "\n".join(
        f'<a href="#pkg-{anchor_of.get(p["base"], 0)}" class="idx-item">'
        f'<b>{html.escape(p["base"])}</b><small>{p["images"]} 图 · {len(p["colors"])} 色</small></a>'
        for p in m["packages"] if p["images"])

    color_html = "\n".join(
        f'<div class="c-item"><span class="c-sw" style="background:{c["rgb"]};'
        f'{"opacity:.55" if c["a"] < 255 else ""}"></span>'
        f'<div><b>{html.escape(c["name"])}</b><small>{c["value"]} · {pkg}</small></div></div>'
        for pkg, c in color_rows[:400])

    declared = set(info["declared_packages"])
    actual = {p["base"] for p in m["packages"]}
    apps = len(actual)
    subs = len(m["packages"])
    missing = sorted(declared - actual)
    extra_pkgs = sorted(actual - declared)
    frames = sum(1 for p in m["packages"] for f in p["files"]
                 if f["kind"] == "image" and re.search(r"_(\d+)\.png$", f["path"]))

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(info['summary'] or '主题资源')} · 资源解析</title>
<style>
:root{{--bg:#08090c;--panel:#12151c;--line:rgba(255,255,255,.08);--ink:#eef2f8;--ink2:#9aa4b4;--ink3:#606a7a;--acc:#7c4dff;--acc2:#c6b8ff}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:radial-gradient(900px 500px at 15% -5%,rgba(124,77,255,.14),transparent 60%),var(--bg);
color:var(--ink);font:14px/1.6 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;padding:28px 30px 80px}}
h1{{font-size:24px;font-weight:650;letter-spacing:.3px}}
.sub{{color:var(--ink3);font-size:12.5px;margin-top:4px}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0 24px}}
.stat{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 18px;min-width:104px}}
.stat b{{display:block;font-size:20px;font-weight:650;color:var(--acc2);letter-spacing:.5px}}
.stat small{{color:var(--ink3);font-size:11px}}
.bar{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:22px}}
.idx-item{{background:rgba(255,255,255,.03);border:1px solid var(--line);border-radius:10px;
padding:8px 12px;text-decoration:none;color:var(--ink);transition:.15s}}
.idx-item:hover{{border-color:var(--acc);background:rgba(124,77,255,.1)}}
.idx-item b{{display:block;font-size:12px;font-weight:600}}
.idx-item small{{color:var(--ink3);font-size:10.5px}}
h2.sec{{font-size:13px;letter-spacing:1px;text-transform:uppercase;color:var(--ink3);
margin:34px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line)}}
.pkg{{margin-bottom:34px}}
.pkg header{{display:flex;align-items:baseline;justify-content:space-between;gap:16px;margin-bottom:6px}}
.pkg h2{{font-size:16px;font-weight:600}}
.pkg h2 em{{font-style:normal;font-size:11.5px;color:var(--ink3);margin-left:8px;font-family:Consolas,monospace}}
.pkg .meta{{font-size:11.5px;color:var(--ink3)}}
.pkg .dir{{font-size:10.5px;color:var(--ink3);font-family:Consolas,monospace;margin-bottom:10px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:10px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:11px;overflow:hidden;transition:.15s}}
.card:hover{{border-color:var(--acc);transform:translateY(-2px)}}
.thumb{{display:grid;place-items:center;height:104px;background:
linear-gradient(45deg,#151a24 25%,#1a2030 25%,#1a2030 50%,#151a24 50%,#151a24 75%,#1a2030 75%);
background-size:16px 16px}}
.thumb img{{max-width:100%;max-height:100%;object-fit:contain;display:block}}
figcaption{{padding:7px 8px;border-top:1px solid var(--line)}}
figcaption b{{display:block;font-size:10px;font-weight:500;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis;color:var(--ink2)}}
figcaption small{{font-size:9.5px;color:var(--ink3);font-family:Consolas,monospace}}
.tg{{font-style:normal;font-size:8px;padding:0 3px;border-radius:3px;margin-left:3px}}
.tg9{{background:rgba(255,180,80,.18);color:#ffb86b}}
.tgw{{background:rgba(120,200,255,.16);color:#79c8ff}}
.more{{margin-top:10px;background:rgba(255,255,255,.04);border:1px solid var(--line);
color:var(--ink2);border-radius:9px;padding:7px 14px;font-size:12px;cursor:pointer}}
.more-row{{display:flex;gap:8px;flex-wrap:wrap}}
.more:hover{{border-color:var(--acc);color:var(--ink)}}
.colors{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:6px}}
.c-item{{display:flex;gap:9px;align-items:center;background:rgba(255,255,255,.025);
border:1px solid var(--line);border-radius:9px;padding:6px 9px}}
.c-sw{{width:22px;height:22px;border-radius:6px;flex:0 0 auto;border:1px solid rgba(255,255,255,.22)}}
.colors-wrap summary{{cursor:pointer;color:var(--acc2);font-size:12.5px;padding:8px 0;list-style:none}}
.colors-wrap summary::-webkit-details-marker{{display:none}}
.colors-wrap summary::before{{content:"▸ "}}
.colors-wrap[open] summary::before{{content:"▾ "}}
.c-item b{{display:block;font-size:10.5px;font-weight:500;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis;max-width:190px}}
.c-item small{{font-size:9.5px;color:var(--ink3);font-family:Consolas,monospace}}
.note{{background:rgba(255,180,80,.07);border:1px solid rgba(255,180,80,.25);border-radius:12px;
padding:14px 16px;margin:18px 0;font-size:12.5px;color:#e8c99b;line-height:1.8}}
.note b{{color:#ffb86b}}
.search{{position:sticky;top:0;z-index:5;background:rgba(8,9,12,.92);backdrop-filter:blur(10px);
padding:10px 0;margin-bottom:8px}}
.search input{{width:100%;max-width:420px;height:38px;border-radius:10px;padding:0 14px;
background:rgba(255,255,255,.05);border:1px solid var(--line);color:var(--ink);font-size:13px}}
.search input:focus{{outline:none;border-color:var(--acc)}}
</style>
</head>
<body>

<h1>{html.escape(info['summary'] or '未命名主题')}</h1>
<div class="sub">
  作者 {html.escape(info['author'] or '—')} ·
  EditorVersion {html.escape(info['editor_version'])} ·
  UUID {html.escape(info['uuid'])} ·
  源文件 {human(m['file_size'])}<br>
  {html.escape(os.path.basename(m['source']))}
</div>

<div class="stats">
  <div class="stat"><b>{st['packages']}</b><small>子包</small></div>
  <div class="stat"><b>{st['images']}</b><small>图片资源</small></div>
  <div class="stat"><b>{human(st['image_bytes'])}</b><small>图片解压后</small></div>
  <div class="stat"><b>{st['colors']}</b><small>颜色条目</small></div>
  <div class="stat"><b>{st['unique_colors']}</b><small>唯一色值</small></div>
  <div class="stat"><b>{len(m['top_files'])}</b><small>顶层文件</small></div>
</div>

<div class="bar">{idx}</div>

<div class="note">
  <b>解析结论</b><br>
  · 声明 {len(declared)} 个包，实际 {subs} 个子包（分属 {apps} 个应用）{('；<b>缺失</b>：' + html.escape('、'.join(missing))) if missing else ''}{('；<b>未声明</b>：' + html.escape('、'.join(extra_pkgs))) if extra_pkgs else ''}<br>
  · 图片格式：{html.escape(' / '.join(f'{k or "无扩展名"} {v} 张' for k, v in st['formats'].items()))}；序列帧 {frames} 张<br>
  · 所有资源已按原路径导出到 <code>packages/</code>，点缩略图可打开原图
</div>

<div class="search"><input id="q" placeholder="搜索文件名，例如 fingerprint / window_background / ota"></div>

<h2 class="sec">图片资源 · {st['images']} 张</h2>
{''.join(pkg_html)}

<h2 class="sec">配色表 · {len(color_rows)} 条（已去重）</h2>
<details class="colors-wrap">
  <summary>展开 {len(color_rows)} 个颜色条目</summary>
  <div class="colors">{color_html}</div>
</details>

<script>
const q = document.getElementById('q');
q.addEventListener('input', () => {{
  const v = q.value.trim().toLowerCase();
  document.querySelectorAll('.card').forEach(c => {{
    const t = c.querySelector('b').textContent.toLowerCase();
    const hit = !v || t.includes(v);
    c.style.display = hit ? '' : 'none';
    if (v) c.hidden = false;
    else if (c.dataset.late) c.hidden = true;
  }});
  document.querySelectorAll('.pkg').forEach(s => {{
    const vis = [...s.querySelectorAll('.card')].some(c => c.style.display !== 'none');
    s.style.display = vis ? '' : 'none';
  }});
}});
document.querySelectorAll('.more').forEach(b => {{
  b.addEventListener('click', () => {{
    const stem = b.dataset.seq;
    document.querySelectorAll('.card').forEach(c => {{
      if (c.dataset.seq === stem) c.hidden = false;
    }});
    b.remove();
  }});
}});
</script>
</body>
</html>
"""


def sequence_map(items: list[dict], min_len: int = 10, preview: int = 4) -> dict[str, tuple]:
    """按「去掉尾部数字」分组识别序列帧,返回 path -> (stem, index, total)"""
    buckets: dict[str, list] = defaultdict(list)
    for f in items:
        name = os.path.basename(f["path"])
        m = re.match(r"^(.*?)_(\d+)\.(png|jpg|jpeg|webp)$", name, re.I)
        if m:
            buckets[m.group(1)].append((int(m.group(2)), f))
    out = {}
    for stem, group in buckets.items():
        if len(group) >= min_len:
            group.sort(key=lambda x: x[0])
            for i, (_, f) in enumerate(group):
                out[f["path"]] = (stem, i, len(group))
    return out


def main():
    ap = argparse.ArgumentParser(description="ColorOS 主题解析导出器")
    ap.add_argument("theme", help=".theme 文件路径")
    ap.add_argument("--out", default="", help="输出目录,默认 exports/<主题名>")
    args = ap.parse_args()

    path = args.theme
    if not os.path.isfile(path):
        sys.exit(f"文件不存在: {path}")

    name = os.path.splitext(os.path.basename(path))[0]
    out = args.out or os.path.join("exports", safe_dirname(name))

    print(f"解析: {path}")
    m = extract(path, out)
    st = m["stats"]
    print(f"完成 → {out}")
    print(f"  {st['packages']} 个包 / {st['images']} 张图片 / {st['colors']} 个颜色")
    print(f"  报告: {os.path.join(out, 'report.html')}")


if __name__ == "__main__":
    main()
