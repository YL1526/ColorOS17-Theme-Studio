"""
ColorOS 17 第三方主题引擎
------------------------------------------------
负责:主题包(.theme)解析 / 配色变换 / 壁纸与图标处理 / 重新打包

ColorOS 主题包格式(依据实机 ColorOS 17 主题逆向结构):
    xxx.theme                       <- 一个 ZIP 容器
    ├── themeInfo.xml               <- 主题元信息(作者、名称、UUID、包清单)
    ├── wkydnsn.xml                 <- 作者水印/说明(可选,原样保留)
    ├── assets                      <- 全局配置子包(assets/colors.xml)
    ├── framework-res               <- 全局配色子包
    ├── com.android.systemui        <- 状态栏/通知/控制中心
    ├── com.android.settings        <- 设置
    ├── com.android.launcher        <- 桌面(图标蒙版/缩放)
    ├── com.android.contacts_002    <- 通话/联系人(文件名 = 包名_版本号)
    ├── ...                         <- 其它应用子包
    ├── icons                       <- 图标包(allApps.xml + res/drawable-xxhdpi/*.png)
    ├── wallpaper                   <- 壁纸包(桌面 + 锁屏)
    └── picture/res/.../preview_*.jpg  <- 商店预览图(可能是目录形式直接平铺)

每个子包同样是一个 ZIP,内部:
    assets/colors.xml               <- 覆盖系统颜色资源(<color name="x">#AARRGGBB</color>)
    colors.xml                      <- 部分包把配色放在根目录
    res/drawable-xxhdpi/**          <- 覆盖系统图片资源
    themeInfo.xml                   <- 部分包带私有参数(如 launcher 的 Scale 缩放)
"""

from __future__ import annotations

import colorsys
import io
import math
import os
import re
import time
import uuid as _uuid
import zipfile
import zlib
from dataclasses import dataclass, field
from typing import Iterable

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ZIP_MAGIC = b"PK\x03\x04"
XML_DECL = '<?xml version="1.0" encoding="utf-8"?>'

# --------------------------------------------------------------------------
# 颜色工具
# --------------------------------------------------------------------------

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3,8})$")


def parse_hex(value: str) -> tuple[int, int, int, int] | None:
    """解析 Android 颜色串,支持 #RGB / #ARGB / #RRGGBB / #AARRGGBB"""
    if not value:
        return None
    m = _HEX_RE.match(value.strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "f" + "".join(c * 2 for c in h)
    elif len(h) == 4:
        h = "".join(c * 2 for c in h)
    elif len(h) == 6:
        h = "ff" + h
    elif len(h) != 8:
        return None
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4, 6))  # a,r,g,b


def to_hex(a: int, r: int, g: int, b: int) -> str:
    return "#%02X%02X%02X%02X" % (a, r, g, b)


def rgb_to_hls(r: int, g: int, b: int) -> tuple[float, float, float]:
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    return h, l, s


def hls_to_rgb(h: float, l: float, s: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return round(r * 255), round(g * 255), round(b * 255)


@dataclass
class ColorTransform:
    """
    配色变换器。

    工作方式(锚点色保持一致):
      模板里出现最多的"强调色"作为锚点(anchor),
      用户选定的颜色作为目标(target),
      计算两者的色相差 ΔH 与饱和度比例 sRatio,
      然后对模板中每一个非中性色做: H = H + ΔH, S = S * f(sRatio), L 保持不变。
    这样能最大程度保留原主题的明暗层次(浅色渐变、半透明遮罩、深色背景都跟着变),
    而不是把几十个色值粗暴替换成同一个颜色。
    """

    target: str = "#FF42D4E4"
    anchor: str = "#FF42D4E4"
    strength: float = 1.0
    hue_only: bool = False
    protect_neutrals: bool = True
    tint_light: bool = False
    overrides: dict[str, str] = field(default_factory=dict)

    _d_h: float = 0.0
    _s_ratio: float = 1.0
    _d_l: float = 0.0
    _span: float = 0.5
    _anchor_l: float = 0.5
    _target_h: float = 0.5

    def prepare(self) -> "ColorTransform":
        t = parse_hex(self.target) or (255, 66, 212, 228)
        a = parse_hex(self.anchor) or (255, 66, 212, 228)
        th, tl, ts = rgb_to_hls(*t[1:])
        ah, al, ass = rgb_to_hls(*a[1:])
        d = th - ah
        if d > 0.5:
            d -= 1.0
        elif d < -0.5:
            d += 1.0
        self._d_h = d
        self._s_ratio = ts / max(ass, 0.06)
        self._d_l = tl - al
        self._anchor_l = al
        self._span = max(al, 1.0 - al, 0.001)
        self._target_h = th
        return self

    def apply(self, value: str) -> str:
        if not value:
            return value
        raw = value.strip()
        key = raw.upper()
        if key in self.overrides:
            return self.overrides[key].upper()

        p = parse_hex(raw)
        if p is None:
            return raw  # @color/xxx 之类引用,原样保留
        a, r, g, b = p
        h, l, s = rgb_to_hls(r, g, b)

        if a == 0:
            return key  # 全透明色,改不改都看不见

        if self.protect_neutrals and s < 0.10:
            # 白灰系模板:可选地把浅色也染上主题色,否则原样保留
            if self.tint_light and l > 0.60:
                r2, g2, b2 = hls_to_rgb(self._target_h, min(l, 0.94),
                                        min(0.40, 0.24 * self.strength))
                return to_hex(a, r2, g2, b2)
            return key

        h2 = (h + self._d_h * self.strength) % 1.0
        if self.hue_only:
            s2, l2 = s, l
        else:
            s2 = min(1.0, max(0.0, s * (1.0 + (self._s_ratio - 1.0) * self.strength)))
            # 明度采用"锚点衰减"曲线:越接近锚点明度的颜色,偏移越完整;
            # 纯黑/纯白端衰减为 0,保证不会把白底刷成彩色。
            falloff = max(0.0, 1.0 - abs(l - self._anchor_l) / self._span)
            l2 = min(1.0, max(0.0, l + self._d_l * falloff * self.strength))
        r2, g2, b2 = hls_to_rgb(h2, l2, s2)
        return to_hex(a, r2, g2, b2)

    def sample(self, value: str) -> str:
        """给前端预览用:返回不带 alpha 的 #RRGGBB"""
        out = self.apply(value)
        p = parse_hex(out)
        if not p:
            return "#888888"
        return "#%02X%02X%02X" % p[1:]


# --------------------------------------------------------------------------
# colors.xml 处理
# --------------------------------------------------------------------------

@dataclass
class ColorEntry:
    name: str
    value: str


def parse_color_xml(data: bytes) -> list[ColorEntry]:
    """从 colors.xml 文本里提取 <color name="x">#...</color>,保留出现顺序与重复项"""
    text = data.decode("utf-8", "replace")
    out: list[ColorEntry] = []
    for m in re.finditer(r"<color\b([^>]*)>([^<]*)</color>", text):
        attrs, val = m.group(1), m.group(2).strip()
        nm = re.search(r'name\s*=\s*"([^"]+)"', attrs)
        if nm and val:
            out.append(ColorEntry(nm.group(1), val))
    return out


def rewrite_colors_xml(data: bytes, transform: ColorTransform | None,
                       overrides: dict[str, str] | None = None) -> bytes:
    """在原文本上做值替换,保留命名空间、注释与排列顺序"""
    overrides = {k.upper(): v for k, v in (overrides or {}).items()}
    text = data.decode("utf-8", "replace")

    def repl(m: re.Match) -> str:
        head, body, tail = m.group(1), m.group(2), m.group(3)
        val = body.strip()
        nm = re.search(r'name\s*=\s*"([^"]+)"', head)
        new = None
        if nm and nm.group(1) in overrides:
            new = overrides[nm.group(1)]
        elif transform is not None and val:
            new = transform.apply(val)
        if not new or new == val:
            return m.group(0)
        return head + new + tail

    text = re.sub(r"(<color\b[^>]*>)([^<]*)(</color>)", repl, text)
    return text.encode("utf-8")


# --------------------------------------------------------------------------
# 子包
# --------------------------------------------------------------------------

@dataclass
class ZipEntry:
    name: str
    info: zipfile.ZipInfo
    data: bytes


class SubPackage:
    """主题内的一个子包(自身也是 ZIP)"""

    def __init__(self, filename: str, raw: bytes):
        self.filename = filename
        self.raw = raw
        self.entries: list[ZipEntry] = []
        self.colorfiles: dict[str, list[ColorEntry]] = {}
        self.modified = False
        self.replacements: dict[str, bytes] = {}
        self.color_overrides: dict[str, dict[str, str]] = {}
        self.added: list[tuple[str, bytes]] = []
        self.removed: set[str] = set()

    # -- 解析 --------------------------------------------------------------
    def load(self) -> "SubPackage":
        try:
            with zipfile.ZipFile(io.BytesIO(self.raw)) as z:
                for info in z.infolist():
                    data = b"" if info.is_dir() else z.read(info.filename)
                    self.entries.append(ZipEntry(info.filename, info, data))
        except zipfile.BadZipFile:
            self.entries = []
            return self
        for e in self.entries:
            if e.name.lower().endswith(".xml") and b"<color" in e.data[:4096]:
                self.colorfiles[e.name] = parse_color_xml(e.data)
        return self

    # -- 能力 --------------------------------------------------------------
    @property
    def has_colors(self) -> bool:
        return bool(self.colorfiles)

    @property
    def base_name(self) -> str:
        return re.sub(r"_\d+$", "", self.filename)

    @property
    def version(self) -> str:
        m = re.search(r"_(\d+)$", self.filename)
        return m.group(1) if m else "001"

    def image_paths(self) -> list[str]:
        return [e.name for e in self.entries
                if not e.name.endswith("/") and e.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]

    def read(self, path: str) -> bytes | None:
        if path in self.replacements:
            return self.replacements[path]
        for e in self.entries:
            if e.name == path:
                return e.data
        return None

    def replace(self, path: str, data: bytes):
        self.replacements[path] = data
        self.modified = True

    def add(self, path: str, data: bytes):
        self.added.append((path, data))
        self.modified = True

    def override_color(self, path: str, name: str, value: str):
        self.color_overrides.setdefault(path, {})[name] = value
        self.modified = True

    # -- 输出 --------------------------------------------------------------
    def build(self, transform: ColorTransform | None) -> bytes:
        need_rebuild = self.modified or (transform is not None and self.has_colors)
        if not need_rebuild:
            return self.raw
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for e in self.entries:
                if e.name in self.removed:
                    continue
                if e.name.endswith("/"):
                    zi = zipfile.ZipInfo(e.name, e.info.date_time)
                    zi.external_attr = e.info.external_attr
                    z.writestr(zi, b"")
                    continue
                data = e.data
                if e.name in self.replacements:
                    data = self.replacements[e.name]
                else:
                    ov = self.color_overrides.get(e.name)
                    if e.name in self.colorfiles and (transform is not None or ov):
                        data = rewrite_colors_xml(data, transform, ov)
                # PNG 本身已压缩,deflate 收益极低,用最低等级换取打包速度
                lvl = 1 if e.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) else 6
                z.writestr(e.name, data, compresslevel=lvl)
            for name, data in self.added:
                if name in self.removed:
                    continue
                lvl = 1 if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) else 6
                z.writestr(name, data, compresslevel=lvl)
        return buf.getvalue()


# --------------------------------------------------------------------------
# 主主题
# --------------------------------------------------------------------------

ROOT_INFO_FIELDS = [
    "Author", "Summary", "Description", "EditorVersion", "LastModifyTime",
    "IsGlobalTheme", "UUID", "PackageName", "StandardVersion",
    "VersionName", "VersionCode", "disableLockPictorial", "enableLauncherApplyEffect",
]


@dataclass
class ThemeInfo:
    author: str = ""
    summary: str = ""
    description: str = ""
    uuid: str = ""
    package_name: str = ""
    version_name: str = "1.0.0"
    version_code: str = "1"
    editor_version: str = "17000"
    last_modify: str = ""
    is_global: str = "1"
    extra_packages: list[str] = field(default_factory=list)


class Theme:
    """一个 .theme 主题包"""

    def __init__(self, path: str):
        self.path = path
        self.entries: list[ZipEntry] = []
        self.packages: dict[str, SubPackage] = {}
        self.info_raw: bytes = b""
        self.info = ThemeInfo()
        self._assets_cache: list[dict] | None = None
        self._base_entries: list[tuple] = []

    # -- 解析 --------------------------------------------------------------
    def load(self) -> "Theme":
        with zipfile.ZipFile(self.path) as z:
            for info in z.infolist():
                data = b"" if info.is_dir() else z.read(info.filename)
                self.entries.append(ZipEntry(info.filename, info, data))
        for e in self.entries:
            if e.name == "themeInfo.xml":
                self.info_raw = e.data
            elif not e.name.endswith("/") and data_is_zip(e.data):
                pkg = SubPackage(e.name, e.data).load()
                if pkg.entries:
                    self.packages[e.name] = pkg
        self.info = self._parse_info()
        # 原始快照:每次构建都从这里还原,避免多次生成互相污染
        self._base_entries = [(e.name, e.info, e.data) for e in self.entries]
        return self

    def _parse_info(self) -> ThemeInfo:
        text = self.info_raw.decode("utf-8", "replace")
        info = ThemeInfo()

        def get(tag: str) -> str:
            m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), text, re.S)
            return m.group(1).strip() if m else ""

        info.author = get("Author")
        info.summary = get("Summary")
        info.description = get("Description")
        info.uuid = get("UUID")
        info.package_name = get("PackageName")
        info.version_name = get("VersionName") or "1.0.0"
        info.version_code = get("VersionCode") or "1"
        info.editor_version = get("EditorVersion") or "17000"
        info.last_modify = get("LastModifyTime")
        info.is_global = get("IsGlobalTheme") or "1"
        info.extra_packages = re.findall(r'<package\s+name="([^"]+)"', text)
        return info

    # -- 统计 --------------------------------------------------------------
    def all_colors(self) -> list[tuple[str, str, str, str]]:
        """(包名, 文件, 颜色名, 值)"""
        out = []
        for pkg in self.packages.values():
            for f, entries in pkg.colorfiles.items():
                for ce in entries:
                    out.append((pkg.filename, f, ce.name, ce.value))
        return out

    def color_stats(self) -> dict:
        counter: dict[str, int] = {}
        for _, _, _, v in self.all_colors():
            k = v.strip().upper()
            counter[k] = counter.get(k, 0) + 1

        items = []
        for hexv, cnt in sorted(counter.items(), key=lambda kv: -kv[1]):
            p = parse_hex(hexv)
            if not p:
                continue
            h, l, s = rgb_to_hls(*p[1:])
            items.append({
                "hex": hexv,
                "rgb": "#%02X%02X%02X" % p[1:],
                "count": cnt,
                "alpha": p[0],
                "h": round(h * 360, 1),
                "l": round(l * 100, 1),
                "s": round(s * 100, 1),
                "neutral": s < 0.10,
            })

        chromatic = [i for i in items if not i["neutral"]]
        anchor = chromatic[0]["hex"] if chromatic else "#FF42D4E4"
        return {
            "anchor": anchor,
            "total": len(items),
            "swatches": items[:24],
            "chromatic": len(chromatic),
        }

    def package_summary(self) -> list[dict]:
        out = []
        for name, pkg in self.packages.items():
            imgs = pkg.image_paths()
            out.append({
                "file": name,
                "base": pkg.base_name,
                "version": pkg.version,
                "colors": sum(len(v) for v in pkg.colorfiles.values()),
                "images": len(imgs),
                "size": len(pkg.raw),
            })
        out.sort(key=lambda x: (-x["colors"], x["file"]))
        return out

    def find_package(self, base: str) -> SubPackage | None:
        for name, pkg in self.packages.items():
            if pkg.base_name == base:
                return pkg
        return None

    def wallpapers(self) -> list[dict]:
        out = []
        pkg = self.find_package("wallpaper")
        if not pkg:
            return out
        for path in pkg.image_paths():
            low = path.lower()
            if "keyguard" in low or "lock" in low:
                role = "lock"
            elif "wallpaper" in low:
                role = "home"
            else:
                continue
            data = pkg.read(path)
            try:
                im = Image.open(io.BytesIO(data))
                w, h = im.size
            except Exception:
                w = h = 0
            out.append({"pkg": pkg.filename, "path": path, "role": role,
                        "w": w, "h": h, "size": len(data or b"")})
        return out

    def icon_list(self) -> list[dict]:
        pkg = self.find_package("icons")
        if not pkg:
            return []
        mapping: dict[str, list[str]] = {}
        raw = pkg.read("allApps.xml")
        if raw:
            txt = raw.decode("utf-8", "replace")
            for m in re.finditer(r'<icon\s+name="([^"]+)"\s+package="([^"]+)"', txt):
                mapping.setdefault(m.group(1), []).append(m.group(2))
        out = []
        for path in pkg.image_paths():
            fn = os.path.basename(path)
            if not path.startswith("res/"):
                continue
            w, h = image_size(pkg.read(path))
            out.append({
                "file": fn,
                "path": path,
                "w": w, "h": h,
                "packages": mapping.get(fn, []),
                "system": fn.startswith("ic_launcher_"),
            })
        out.sort(key=lambda x: (x["system"], x["file"]))
        return out

    def asset_list(self) -> list[dict]:
        """
        列出主题里所有可替换的图片资源(含尺寸)。
        同名资源会带上 duplicate_of,提示它同时存在于哪些包里。
        """
        if self._assets_cache is not None:
            return self._assets_cache

        rows: list[dict] = []
        for name, pkg in self.packages.items():
            for path in pkg.image_paths():
                fn = os.path.basename(path)
                data = pkg.read(path) or b""
                w, h = image_size(data)
                rows.append({
                    "pkg": name,
                    "base": pkg.base_name,
                    "path": path,
                    "file": fn,
                    "w": w,
                    "h": h,
                    "kb": round(len(data) / 1024),
                    "nine": fn.endswith(".9.png"),
                })

        # 统计同名副本,便于"联动替换"
        by_file: dict[str, list[dict]] = {}
        for r in rows:
            by_file.setdefault(r["file"], []).append(r)
        for fn, group in by_file.items():
            pkgs = sorted({g["base"] for g in group})
            for r in group:
                r["copies"] = len(group)
                r["copy_bases"] = pkgs

        rows.sort(key=lambda r: (r["base"], r["file"]))
        self._assets_cache = rows
        return rows

    def preview_images(self) -> list[dict]:
        out = []
        for e in self.entries:
            low = e.name.lower()
            if e.name.endswith("/") or not low.endswith((".jpg", ".png", ".jpeg")):
                continue
            if "preview_" in low:
                key = re.sub(r"^.*preview_", "", low)
                key = os.path.splitext(key)[0]
                out.append({"key": key, "path": e.name})
        return out

    # -- 构建 --------------------------------------------------------------
    def build(self, opts: "BuildOptions", out_path: str) -> dict:
        log: list[str] = []
        warnings: list[str] = []

        # 还原到干净状态(模板实例是复用的,上一次的改动不能带过来)
        self.entries = [ZipEntry(n, i, d) for n, i, d in self._base_entries]
        for pkg in self.packages.values():
            pkg.replacements.clear()
            pkg.removed.clear()
            pkg.added.clear()

        transform = opts.color_transform()
        if transform:
            log.append(f"配色变换: 锚点 {transform.anchor} → 目标 {transform.target} "
                       f"(色相 {transform._d_h * 360:+.1f}°, 饱和 ×{transform._s_ratio:.2f})")

        # 1. 壁纸
        if opts.wallpaper or opts.lockscreen:
            pkg = self.find_package("wallpaper")
            if not pkg:
                warnings.append("模板中没有 wallpaper 包,壁纸未应用")
            else:
                for role, blob in (("home", opts.wallpaper), ("lock", opts.lockscreen)):
                    if not blob:
                        continue
                    target = next((w for w in self.wallpapers() if w["role"] == role), None)
                    if not target:
                        warnings.append(f"未找到{'锁屏' if role == 'lock' else '桌面'}壁纸目标,已跳过")
                        continue
                    fmt = "JPEG" if target["path"].lower().endswith((".jpg", ".jpeg")) else "PNG"
                    size = (target["w"] or 1080, target["h"] or 2400)
                    pkg.replace(target["path"], wallpaper_image(blob, size, fmt, opts.wallpaper_fit))
                    log.append(f"壁纸[{role}] → {target['path']} ({size[0]}×{size[1]}, {opts.wallpaper_fit})")

        # 2. 图标
        if opts.icons or opts.icon_shape or opts.icon_scale or opts.icon_remove:
            pkg = self.find_package("icons")
            if not pkg:
                warnings.append("模板中没有 icons 包,图标未应用")
            else:
                paths = {os.path.basename(p): p for p in pkg.image_paths()}
                default_size = 168
                for fn, path in paths.items():
                    b = pkg.read(path)
                    if b:
                        try:
                            default_size = Image.open(io.BytesIO(b)).size[0]
                        except Exception:
                            pass
                        break

                # 先删除,再替换/新增(删除的图即使同名也不复活)
                removed = 0
                for fn in opts.icon_remove:
                    safe = os.path.basename(fn)
                    if not safe.lower().endswith(".png"):
                        safe += ".png"
                    if safe in paths:
                        pkg.removed.add(paths[safe])
                        paths.pop(safe, None)
                        removed += 1
                if removed:
                    self._unregister_icons(pkg, [os.path.basename(x) for x in opts.icon_remove])
                    log.append(f"图标移除: {removed} 个")

                added_icons = []
                for fn, blob in (opts.icons or {}).items():
                    safe = os.path.basename(fn)
                    if not safe.lower().endswith(".png"):
                        safe += ".png"
                    if safe in paths:
                        pkg.replace(paths[safe], normalize_icon(blob, default_size))
                        log.append(f"图标替换: {safe}")
                    else:
                        tgt = f"res/drawable-xxhdpi/{safe}"
                        pkg.add(tgt, normalize_icon(blob, default_size))
                        paths[safe] = tgt
                        added_icons.append(safe)
                        log.append(f"图标新增: {safe}")
                if added_icons:
                    # 包名没显式给时,从文件名自动推导(com.xxx.yyy.png → com.xxx.yyy)
                    pkgs = dict(opts.icon_packages or {})
                    for f in added_icons:
                        if f not in pkgs:
                            guess = os.path.splitext(f)[0]
                            if re.fullmatch(r"[A-Za-z][\w-]*(\.[\w-]+)+", guess):
                                pkgs[f] = guess
                    self._register_icons(pkg, added_icons, pkgs)
                if opts.icon_shape:
                    self._apply_icon_shape(pkg, opts.icon_shape, default_size)
                    log.append(f"图标形状: {opts.icon_shape}")

            if opts.icon_scale:
                lp = self.find_package("com.android.launcher")
                if lp:
                    raw = lp.read("themeInfo.xml")
                    if raw:
                        txt = raw.decode("utf-8", "replace")
                        txt2 = re.sub(r"<Scale>[^<]*</Scale>", f"<Scale>{opts.icon_scale:.2f}</Scale>", txt)
                        if txt2 != txt:
                            lp.replace("themeInfo.xml", txt2.encode("utf-8"))
                            log.append(f"图标缩放: {opts.icon_scale:.2f}")

        # 3. 状态栏图标着色
        if opts.tint_systemui:
            pkg = self.find_package("com.android.systemui")
            if pkg:
                tint = parse_hex(opts.tint_color or opts.primary)
                n = 0
                for path in pkg.image_paths():
                    fn = os.path.basename(path).lower()
                    if not (fn.startswith("stat_") or fn.startswith("status_bar_qs_icon")):
                        continue
                    if "bg" in fn or "pb" in fn:
                        continue
                    b = pkg.read(path)
                    if not b:
                        continue
                    try:
                        pkg.replace(path, tint_png(b, tint))
                        n += 1
                    except Exception:
                        pass
                log.append(f"状态栏图标着色: {n} 个")

        # 4. 界面资源(设置背景、音量面板、关于本机动画帧…)
        if opts.assets:
            self._apply_assets(opts, log, warnings)

        # 5. 预览图
        if opts.previews or opts.preview_add or opts.preview_remove:
            self._apply_previews(opts.previews, opts.preview_add,
                                 opts.preview_remove, log, warnings)
        # 6. 顶级元信息
        new_info = self._render_info(opts)
        log.append(f"主题信息: {opts.name} / {opts.author} / UUID {opts.uuid}")

        # 7. 打包
        tmp = out_path + ".part"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for e in self.entries:
                if e.name == "themeInfo.xml":
                    z.writestr(e.name, new_info)
                    continue
                pkg = self.packages.get(e.name)
                if pkg is not None:
                    z.writestr(e.name, pkg.build(transform), compresslevel=1)
                else:
                    lvl = 1 if e.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) else 6
                    z.writestr(e.name, e.data, compresslevel=lvl)
        os.replace(tmp, out_path)

        return {
            "path": out_path,
            "size": os.path.getsize(out_path),
            "log": log,
            "warnings": warnings,
        }

    # -- 内部 --------------------------------------------------------------
    def _apply_assets(self, opts: "BuildOptions", log: list[str], warnings: list[str]):
        """替换界面图片资源;同名资源可跨包联动替换"""
        for item in opts.assets:
            fn = item.get("file")
            blob = item.get("data")
            if not fn or not blob:
                continue
            want_pkg = item.get("pkg") or ""
            sync = item.get("sync", True)
            mode = item.get("fit") or opts.asset_fit or "cover"

            pairs = [(p, path) for p in self.packages.values()
                     for path in p.image_paths() if os.path.basename(path) == fn]
            if not pairs:
                warnings.append(f"模板里没有找到资源 {fn}")
                continue

            if sync:
                targets = pairs
            elif want_pkg:
                targets = [t for t in pairs if t[0].filename == want_pkg][:1]
            else:
                targets = pairs[:1]
            if not targets:
                warnings.append(f"{want_pkg} 里没有 {fn}")
                continue

            done = 0
            cache: dict[tuple, bytes] = {}
            for pkg, path in targets:
                orig = pkg.read(path) or b""
                ow, oh = image_size(orig)
                if ow == 0:
                    continue
                key = (ow, oh, mode, zlib.crc32(orig))
                try:
                    if key in cache:
                        new = cache[key]
                    elif path.lower().endswith(".9.png"):
                        new = replace_nine_patch(orig, blob, mode, opts.asset_compress)
                    else:
                        new = fit_asset(blob, (ow, oh), mode)
                        if opts.asset_compress and ow * oh > 500_000:
                            new = quantize_png(new)
                    cache[key] = new
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"{fn} 处理失败: {exc}")
                    continue
                pkg.replace(path, new)
                done += 1

            where = "、".join(sorted({t[0].base_name for t in targets})) if len(targets) > 1 else targets[0][0].base_name
            log.append(f"界面资源: {fn} → {done} 处 ({ow}×{oh}  {where})")

    def _register_icons(self, pkg: SubPackage, new_files: list[str], packages: dict[str, str]):
        raw = pkg.read("allApps.xml")
        if not raw:
            return
        txt = raw.decode("utf-8", "replace")
        lines = []
        for fn in new_files:
            pk = packages.get(fn)
            if not pk:
                continue
            lines.append(f'\t<icon name="{fn}" package="{pk}" />')
        if not lines:
            return
        marker = "</iconinfo>"
        txt = txt.replace(marker, "\n".join(lines) + "\n" + marker)
        pkg.replace("allApps.xml", txt.encode("utf-8"))

    def _unregister_icons(self, pkg: SubPackage, files: list[str]):
        """从 allApps.xml 里删掉这些图标的映射"""
        raw = pkg.read("allApps.xml")
        if not raw:
            return
        txt = raw.decode("utf-8", "replace")
        keep = [ln for ln in txt.splitlines()
                if not any(f'name="{f}"' in ln and "<icon" in ln for f in files)]
        if len(keep) != len(txt.splitlines()):
            pkg.replace("allApps.xml", "\n".join(keep).encode("utf-8"))

    def _apply_icon_shape(self, pkg: SubPackage, shape: str, size: int):
        target = None
        for path in pkg.image_paths():
            if "mask" in os.path.basename(path).lower():
                target = path
                break
        if not target:
            return
        pkg.replace(target, make_mask(shape, size))

    def _apply_previews(self, previews: dict[str, bytes], adds: list[dict],
                        removes: list[str], log: list[str], warnings: list[str]):
        """预览图的增删改：先删，再改，最后加"""
        # 先记下原始参考(尺寸/目录),删完再取就没了
        ref_w, ref_h = 2520, 1080
        ref_dir = "picture/res/drawable-xxhdpi"
        base_previews = self.preview_images()
        if base_previews:
            ref_dir = os.path.dirname(base_previews[0]["path"]) or ref_dir
            for e in self.entries:
                if e.name == base_previews[0]["path"]:
                    try:
                        ref_w, ref_h = Image.open(io.BytesIO(e.data)).size
                    except Exception:
                        pass
                    break

        rm = [r for r in (removes or []) if r]
        if rm:
            keep = [e for e in self.entries if e.name not in rm]
            n = len(self.entries) - len(keep)
            self.entries = keep
            for pkg in self.packages.values():
                for p in rm:
                    if pkg.read(p) is not None:
                        pkg.removed.add(p)
            if n:
                log.append(f"预览图删除: {n} 张")

        known = {p["key"]: p["path"] for p in self.preview_images()}

        for key, blob in (previews or {}).items():
            path = known.get(key)
            if not path:
                warnings.append(f"模板缺少预览图槽位: {key}")
                continue
            fmt = "JPEG" if path.lower().endswith((".jpg", ".jpeg")) else "PNG"
            hit = False
            for e in self.entries:
                if e.name == path:
                    try:
                        w, h = Image.open(io.BytesIO(e.data)).size
                    except Exception:
                        w, h = 2520, 1080
                    e.data = fit_image(blob, (w, h), fmt)
                    hit = True
                    break
            if hit:
                log.append(f"预览图替换: {key}")
            else:
                for pkg in self.packages.values():
                    if pkg.read(path) is not None:
                        try:
                            w, h = Image.open(io.BytesIO(pkg.read(path))).size
                        except Exception:
                            w, h = 2520, 1080
                        pkg.replace(path, fit_image(blob, (w, h), fmt))
                        log.append(f"预览图替换: {key}")
                        break

        # 新增
        adds = [a for a in (adds or []) if a.get("data")]
        if adds:
            tw, th = ref_w, ref_h
            folder = ref_dir
            existing = {e.name for e in self.entries}
            for item in adds:
                name = os.path.basename(item.get("name") or "preview_extra.png")
                if not name.lower().endswith((".png", ".jpg", ".jpeg")):
                    name += ".png"
                path = f"{folder}/{name}"
                if path in existing:
                    warnings.append(f"预览图已存在,跳过: {name}")
                    continue
                fmt = "JPEG" if name.lower().endswith((".jpg", ".jpeg")) else "PNG"
                data = fit_image(item["data"], (tw, th), fmt)
                self.entries.append(ZipEntry(path, zipfile.ZipInfo(path), data))
                existing.add(path)
                log.append(f"预览图新增: {name} ({tw}×{th})")

    def _render_info(self, opts: "BuildOptions") -> bytes:
        text = self.info_raw.decode("utf-8", "replace") if self.info_raw else (
            XML_DECL + "\n<OplusSmartPhoneThemeInfo>\n</OplusSmartPhoneThemeInfo>\n"
        )
        values = {
            "Author": opts.author,
            "Summary": opts.name,
            "Description": opts.description,
            "VersionName": opts.version_name,
            "VersionCode": str(opts.version_code),
            "UUID": opts.uuid,
            "PackageName": opts.uuid,
            "LastModifyTime": time.strftime("%Y-%m-%d %H:%M:%S"),
            "EditorVersion": str(opts.editor_version or "17000"),
            "IsGlobalTheme": "1" if opts.is_global else "0",
        }
        for tag, val in values.items():
            text = _set_tag(text, tag, val)
        if not opts.description:
            text = _set_tag(text, "Description", "")
        return text.encode("utf-8")


def _set_tag(text: str, tag: str, value: str) -> str:
    esc = (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    pat = re.compile(r"<%s>.*?</%s>" % (tag, tag), re.S)
    if pat.search(text):
        return pat.sub(lambda m: "<%s>%s</%s>" % (tag, esc, tag), text, count=1)
    close = "</OplusSmartPhoneThemeInfo>"
    if close in text:
        return text.replace(close, "  <%s>%s</%s>\n%s" % (tag, esc, tag, close), 1)
    return text


def data_is_zip(data: bytes) -> bool:
    return data[:4] == ZIP_MAGIC


# --------------------------------------------------------------------------
# 图像处理
# --------------------------------------------------------------------------

def image_size(data: bytes | None) -> tuple[int, int]:
    if not data:
        return (0, 0)
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:
        return (0, 0)


def quantize_png(data: bytes, colors: int = 256) -> bytes:
    """把照片类 PNG 降到 256 色,体积通常减半(alpha 通道单独保留)"""
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    alpha = im.split()[3]
    rgb = im.convert("RGB").quantize(colors=colors, method=Image.FASTOCTREE).convert("RGB")
    out_im = rgb.convert("RGBA")
    out_im.putalpha(alpha)
    out = io.BytesIO()
    out_im.save(out, "PNG", compress_level=6)
    return out.getvalue()


def replace_nine_patch(orig_bytes: bytes, blob: bytes, mode: str = "cover",
                       compress: bool = True) -> bytes:
    """
    安全替换 .9.png:
    九宫格拉伸标记画在图片最外 1px 的边框上,直接缩放会破坏标记导致界面错位。
    做法 = 新图缩放进内容区(去掉 1px 边框),再把原图四条边框原样贴回去。
    """
    orig = Image.open(io.BytesIO(orig_bytes)).convert("RGBA")
    w, h = orig.size
    iw, ih = max(1, w - 2), max(1, h - 2)
    inner_bytes = fit_asset(blob, (iw, ih), mode)
    if compress and iw * ih > 500_000:
        inner_bytes = quantize_png(inner_bytes)
    inner = Image.open(io.BytesIO(inner_bytes)).convert("RGBA")

    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(inner, (1, 1))
    canvas.paste(orig.crop((0, 0, w, 1)), (0, 0))
    canvas.paste(orig.crop((0, h - 1, w, h)), (0, h - 1))
    canvas.paste(orig.crop((0, 0, 1, h)), (0, 0))
    canvas.paste(orig.crop((w - 1, 0, w, h)), (w - 1, 0))

    out = io.BytesIO()
    canvas.save(out, "PNG", compress_level=6)
    return out.getvalue()


def fit_asset(blob: bytes, size: tuple[int, int], mode: str = "cover",
              nine: bool = False) -> bytes:
    """
    把用户图片处理成目标资源尺寸。
      cover   —— 裁剪铺满
      contain —— 完整显示,四周留透明
    九宫格请用 replace_nine_patch,不要直接调这里。
    """
    if mode != "contain":
        return fit_image(blob, size, "PNG")
    tw, th = max(1, size[0]), max(1, size[1])
    im = Image.open(io.BytesIO(blob)).convert("RGBA")
    im.thumbnail((tw, th), Image.LANCZOS)
    canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    canvas.paste(im, ((tw - im.width) // 2, (th - im.height) // 2), im)
    out = io.BytesIO()
    canvas.save(out, "PNG", compress_level=6)
    return out.getvalue()


def fit_image(blob: bytes, size: tuple[int, int], fmt: str = "JPEG") -> bytes:
    """等比缩放 + 居中裁剪(cover),直接按目标区域一步重采样,快且清晰"""
    im = Image.open(io.BytesIO(blob))
    im = im.convert("RGB" if fmt == "JPEG" else "RGBA")
    tw, th = max(1, size[0]), max(1, size[1])
    ratio = max(tw / im.width, th / im.height)
    cw = min(im.width, tw / ratio)
    ch = min(im.height, th / ratio)
    left = max(0.0, (im.width - cw) / 2)
    top = max(0.0, (im.height - ch) / 2)
    box = (round(left), round(top), round(left + cw), round(top + ch))
    im = im.resize((tw, th), Image.LANCZOS, box=box)
    out = io.BytesIO()
    if fmt == "JPEG":
        im.save(out, "JPEG", quality=93, subsampling=1, optimize=True)
    else:
        im.save(out, "PNG", compress_level=6)
    return out.getvalue()


def wallpaper_image(blob: bytes, size: tuple[int, int], fmt: str = "JPEG",
                    mode: str = "cover") -> bytes:
    """
    生成最终壁纸。
      cover —— 等比放大后居中裁剪,铺满屏幕(默认)
      blur  —— 完整显示原图,四周用原图模糊放大补边(适合横图/方图)
    """
    if mode != "blur":
        return fit_image(blob, size, fmt)

    tw, th = max(1, size[0]), max(1, size[1])
    back = Image.open(io.BytesIO(fit_image(blob, size, "JPEG"))).convert("RGB")
    # 降采样后再模糊,速度快很多,视觉几乎无差别
    sw, sh = max(1, tw // 4), max(1, th // 4)
    back = back.resize((sw, sh), Image.LANCZOS)
    back = back.filter(ImageFilter.GaussianBlur(max(3, tw // 34 // 4)))
    back = back.resize((tw, th), Image.BILINEAR)
    back = ImageEnhance.Brightness(back).enhance(0.84)

    fg = Image.open(io.BytesIO(blob)).convert("RGBA")
    fg.thumbnail((tw, th), Image.LANCZOS)

    if fmt == "JPEG":
        canvas = back.convert("RGB")
        mask = fg.split()[3]
        canvas.paste(fg.convert("RGB"), ((tw - fg.width) // 2, (th - fg.height) // 2), mask)
    else:
        canvas = back.convert("RGBA")
        canvas.alpha_composite(fg, ((tw - fg.width) // 2, (th - fg.height) // 2))

    out = io.BytesIO()
    if fmt == "JPEG":
        canvas.save(out, "JPEG", quality=93, subsampling=1, optimize=True)
    else:
        canvas.save(out, "PNG", optimize=True)
    return out.getvalue()


def normalize_icon(blob: bytes, size: int = 168) -> bytes:
    """把上传的图标处理成正方形 RGBA PNG(等比缩放,透明居中)"""
    im = Image.open(io.BytesIO(blob)).convert("RGBA")
    im.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue()


def tint_png(blob: bytes, argb: tuple[int, int, int, int]) -> bytes:
    """保留 alpha 形状,把颜色刷成目标色"""
    im = Image.open(io.BytesIO(blob)).convert("RGBA")
    alpha = im.split()[3]
    solid = Image.new("RGBA", im.size, (argb[1], argb[2], argb[3], 255))
    solid.putalpha(alpha)
    out = io.BytesIO()
    solid.save(out, "PNG", optimize=True)
    return out.getvalue()


def make_mask(shape: str, size: int = 168) -> bytes:
    """生成图标蒙版(白色形状 + alpha)"""
    s = size * 4  # 超采样,边缘更平滑
    img = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(img)
    if shape == "circle":
        d.ellipse((0, 0, s - 1, s - 1), fill=255)
    elif shape in ("square", "none"):
        d.rectangle((0, 0, s - 1, s - 1), fill=255)
    elif shape == "rounded":
        r = int(s * 0.18)
        d.rounded_rectangle((0, 0, s - 1, s - 1), radius=r, fill=255)
    else:  # squircle:超椭圆
        n = 4.0
        cx = cy = (s - 1) / 2
        a = (s - 1) / 2
        pts = []
        steps = 720
        for i in range(steps):
            t = 2 * math.pi * i / steps
            ct, st = math.cos(t), math.sin(t)
            x = cx + a * math.copysign(abs(ct) ** (2 / n), ct)
            y = cy + a * math.copysign(abs(st) ** (2 / n), st)
            pts.append((x, y))
        d.polygon(pts, fill=255)
    img = img.resize((size, size), Image.LANCZOS)
    out_im = Image.merge("RGBA", (Image.new("L", (size, size), 255),) * 3 + (img,))
    out = io.BytesIO()
    out_im.save(out, "PNG", optimize=True)
    return out.getvalue()


# --------------------------------------------------------------------------
# 构建参数
# --------------------------------------------------------------------------

@dataclass
class BuildOptions:
    name: str = "我的主题"
    author: str = ""
    description: str = ""
    uuid: str = ""
    version_name: str = "1.0.0"
    version_code: int = 1
    editor_version: str = "17000"

    primary: str = "#FF42D4E4"
    anchor: str = ""
    strength: float = 1.0
    hue_only: bool = False
    protect_neutrals: bool = True
    tint_light: bool = False
    color_overrides: dict[str, str] = field(default_factory=dict)
    recolor: bool = True

    wallpaper: bytes | None = None
    lockscreen: bytes | None = None
    wallpaper_fit: str = "cover"
    assets: list[dict] = field(default_factory=list)
    asset_fit: str = "cover"
    asset_compress: bool = True
    is_global: bool = True
    icons: dict[str, bytes] = field(default_factory=dict)
    icon_remove: list[str] = field(default_factory=list)
    icon_packages: dict[str, str] = field(default_factory=dict)
    icon_shape: str = ""
    icon_scale: float = 0.0
    tint_systemui: bool = False
    tint_color: str = ""
    previews: dict[str, bytes] = field(default_factory=dict)
    preview_add: list[dict] = field(default_factory=list)
    preview_remove: list[str] = field(default_factory=list)

    def color_transform(self) -> ColorTransform | None:
        if not self.recolor:
            return None
        t = ColorTransform(
            target=self.primary,
            anchor=self.anchor or self.primary,
            strength=max(0.0, min(2.0, float(self.strength))),
            hue_only=bool(self.hue_only),
            protect_neutrals=bool(self.protect_neutrals),
            tint_light=bool(self.tint_light),
            overrides={k.upper(): v for k, v in self.color_overrides.items()},
        )
        return t.prepare()


def new_uuid() -> str:
    return _uuid.uuid4().hex.upper()
