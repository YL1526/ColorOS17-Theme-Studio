/* ColorOS 17 主题工坊 —— 前端逻辑 */
(() => {
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const S = {
  templates: [],
  tpl: null,
  detail: null,
  step: 'template',
  view: 'home',
  // 配色
  primary: '#FF42D4E4',
  anchor: '#FF42D4E4',
  strength: 1,
  hueOnly: false,
  protect: true,
  tintLight: false,
  recolor: true,
  overrides: {},
  swatches: [],
  // 壁纸
  wallpaper: null,      // upload id
  wallpaperUrl: null,
  lockscreen: null,
  lockscreenUrl: null,
  wallpaperFit: 'cover',
  // 图标
  icons: {},            // filename -> {upload, url, isNew, pkg}
  iconRemoved: [],      // 从主题里移除的图标文件名
  iconShape: '',
  iconScale: 0,
  tint: false,
  iconQuery: '',
  // 界面资源
  assets: {},           // file -> {upload, url}
  previews: {},         // key -> {upload, url, path, name}  path 为空表示新增
  previewRemoved: [],   // 要从包里删掉的预览图路径
  assetData: null,      // /api/assets 返回
  assetFilter: '',
  assetPkg: '',
  assetCat: '',         // 资源分类筛选
  assetFit: 'cover',
  assetCompress: true,
  // 元信息
  name: '',
  author: '',
  description: '',
  versionName: '1.0.0',
  versionCode: 1,
  uuid: '',
  isGlobal: true,
  lastResult: null,
  outputs: [],
  busy: false,
};

const PRESETS = [
  '#FF42D4E4', '#FFFF6FA8', '#FF7C4DFF', '#FF3D7BFF',
  '#FF00C853', '#FFFFA000', '#FFFF4D4F', '#FF9AA4B4',
];

const TPL_KEY = 'costudio.template';

/* 资源 → 预览界面，替换后自动跳过去 */
const ASSET_VIEW = {
  'coui_window_background_selector.9.png': 'settings',
  'coui_window_background_with_card_selector.9.png': 'settings',
  'systemui_panel_volume_bg.9.png': 'volume',
  'pb_bg_dialer.9.png': 'dialer',
  'about_device_top_video_last_frame_17.png': 'about',
  'about_device_top_video_mask.png': 'about',
  'status_bar_qs_media_bg_active.png': 'cc',
  'status_bar_qs_tile_bg_active.png': 'cc',
  'clear_all_icon.png': 'notify',
  'clear_all_bg.png': 'notify',
};

/* 常见应用包名 → 中文名 */
const APP_NAMES = {
  'com.tencent.mm': '微信', 'com.tencent.mobileqq': 'QQ', 'com.tencent.qq': 'QQ',
  'com.taobao.taobao': '淘宝', 'com.eg.android.AlipayGphone': '支付宝',
  'com.ss.android.ugc.aweme': '抖音', 'com.sina.weibo': '微博', 'com.xingin.xhs': '小红书',
  'com.tencent.tmgp.sgame': '王者荣耀', 'com.tencent.tmgp.pubgmhd': '和平精英',
  'com.miHoYo.Yuanshen': '原神', 'com.miHoYo.hkrpg': '星穹铁道',
  'com.miHoYo.Nap': '绝区零', 'com.miHoYo.enterprise.NGHSoD': '崩坏3',
  'com.mihoyo.hyperion': '米游社', 'com.netease.cloudmusic': '网易云音乐',
  'com.tencent.qqmusic': 'QQ音乐', 'com.kugou.android': '酷狗音乐',
  'com.jingdong.app.mall': '京东', 'com.xunmeng.pinduoduo': '拼多多',
  'com.sankuai.meituan': '美团', 'com.sankuai.meituan.takeoutnew': '美团外卖',
  'com.autonavi.minimap': '高德地图', 'com.baidu.netdisk': '百度网盘',
  'com.deepseek.chat': 'DeepSeek', 'com.smile.gifmaker': '快手',
  'com.quark.browser': '夸克', 'com.taobao.idlefish': '闲鱼', 'com.larus.nova': '豆包',
  'com.yek.android.kfc.activitys': '肯德基', 'com.ct.client': '中国电信',
  'com.greenpoint.android.mc10086.activity': '中国移动', 'com.topjohnwu.magisk': 'Magisk',
  'com.omarea.vtools': 'Scene', 'com.perol.pixez': 'PixEz',
  'com.picacg.picacomic': '哔咔', 'com.picacomic.fregata': '哔咔E',
  'com.bigjpg': '图片放大', 'com.handsgo.jiakao.android': '驾考宝典',
  'com.sankuai.meituan': '美团', 'com.tmall.wireless': '天猫',
  'com.tencent.android.pad': 'QQ HD', 'com.baidu.tieba': '贴吧',
  'com.JMComic3.app': 'JM', 'com.tencent.wework': '企业微信',
};
const appName = pkg => APP_NAMES[pkg] || (pkg || '').split('.').pop() || '应用';

const PREVIEW_NAMES = { lock: '锁屏预览', menu: '桌面预览', play: '播放页预览', third: '第三屏预览' };
const PREVIEW_SLOTS = ['lock', 'menu', 'play', 'third'];

/* 商店预览图：4 个标准槽位 + 模板里的额外图 + 自定义添加 */
function previewSection() {
  const existing = S.detail?.previews || [];
  const byKey = {};
  existing.forEach(p => { byKey[p.key] = p; });
  const removed = new Set(S.previewRemoved);

  const card = (key, label, item, isSlot) => {
    const ov = S.previews[key];
    const dead = item && removed.has(item.path);
    const src = ov?.url || (item && !dead ? item.url : '');
    const w = ov?.w || item?.w;
    const h = ov?.h || item?.h;
    const state = ov ? (ov.path ? '已换' : '已加') : '';
    if (!src) {
      return `<div class="pv-card empty" data-preview="${esc(key)}">
        <span class="pv-plus">＋</span><b>${label}</b><small>点击添加</small></div>`;
    }
    return `<div class="pv-card" data-preview="${esc(key)}" title="${esc(item?.path || label)}">
      <img src="${src}" alt="">
      <b>${label}</b>
      <small>${w && h ? `${w}×${h}` : ''}${state ? ' · ' + state : ''}</small>
      <i class="pv-del" data-pvdel="${esc(key)}" title="${isSlot ? '删除这张' : '移除'}">×</i>
    </div>`;
  };

  const slotCards = PREVIEW_SLOTS.map(k => card(k, PREVIEW_NAMES[k], byKey[k], true)).join('');
  const extraKeys = Object.keys(byKey).filter(k => !PREVIEW_SLOTS.includes(k));
  const extras = extraKeys.map(k => card(k, byKey[k].key, byKey[k], false)).join('');

  return `<div class="pv-grid">${slotCards}${extras}</div>
    <button class="pv-add" data-act="addPreview">＋ 再加一张（自定义）</button>`;
}

/* 界面资源里最常改的几个位置 */
const QUICK_ASSETS = [
  { file: 'coui_window_background_selector.9.png', name: '设置 / 短信背景', note: '设置、短信、电话、全局共用，5 个包联动' },
  { file: 'coui_window_background_with_card_selector.9.png', name: '设置背景（卡片版）', note: '带卡片的页面用' },
  { file: 'systemui_panel_volume_bg.9.png', name: '音量面板', note: '按音量键弹出的面板底色' },
  { file: 'about_device_top_video_last_frame_17.png', name: '关于本机顶部大图', note: '就是那张 ColorOS / Miku OS 图' },
  { file: 'about_device_top_video_mask.png', name: '关于本机遮罩', note: '和上一张配套，一起换' },
  { file: 'status_bar_qs_media_bg_active.png', name: '控制中心媒体卡', note: '媒体播放卡片底板' },
  { file: 'device_ota_card_bg_new.png', name: '系统更新卡片', note: 'OTA 提示卡背景' },
  { file: 'pb_bg_dialer.9.png', name: '拨号盘背景', note: '电话 App 拨号页' },
  { file: 'clear_all_icon.png', name: '一键清理图标', note: '最近任务里的清空按钮' },
  { file: 'brand_logo.png', name: '品牌 Logo 蒙版', note: '纯白蒙版，由系统染色' },
];

/* 资源分类（用于「全部资源」的分组筛选与中文说明） */
const ASSET_CATS = [
  { key: 'window',  name: '窗口/列表背景', icon: '▦' },
  { key: 'cc',      name: '控制中心',     icon: '◉' },
  { key: 'statusbar', name: '状态栏图标', icon: '▤' },
  { key: 'battery', name: '电池',         icon: '▮' },
  { key: 'dialer',  name: '拨号盘',       icon: '☏' },
  { key: 'settings-ic', name: '设置项图标', icon: '⚙' },
  { key: 'about',   name: '关于本机',     icon: 'ⓘ' },
  { key: 'lock',    name: '锁屏/指纹',    icon: '☾' },
  { key: 'notify',  name: '通知',         icon: '◈' },
  { key: 'launch',  name: '启动/Logo',    icon: '◇' },
  { key: 'misc',    name: '其他',         icon: '·' },
];
const CAT_ORDER = ASSET_CATS.map(c => c.key);

/* 分类规则：按文件名关键词归类（从上往下第一个命中生效） */
const CAT_RULES = [
  { key: 'about',   re: /about_device/ },
  { key: 'dialer',  re: /^pb_bg_/ },
  { key: 'settings-ic', re: /^settings_.*_ic\./ },
  { key: 'lock',    re: /fingerprint|kgd_|darkmode_sketch|lightmode_sketch/ },
  { key: 'notify',  re: /notification_|clear_all/ },
  { key: 'cc',      re: /status_bar_qs_|systemui_panel_volume|quicksettings_slider|status_(rectangle|square|nodevice)_card/ },
  { key: 'battery', re: /^stat_battery|^stat_bt_battery/ },
  { key: 'statusbar', re: /^stat_signal_|^stat_sys_|^stat_notification_/ },
  { key: 'launch',  re: /brand_logo|splash|start_slogan|^icon_|ic_launcher|ic_foreground|android12splash/ },
  { key: 'window',  re: /coui_|toolbar|tablayout|tab_navigation|list_sort|search_view|searchview/ },
  { key: 'misc',    re: /./ },
];
function assetCat(file) {
  for (const r of CAT_RULES) if (r.re.test(file)) return r.key;
  return 'misc';
}

/* 逐文件的中文用途说明（精确匹配优先；没命中走 describeAsset 推断） */
const ASSET_DESC = {
  'coui_window_background_selector.9.png': '全局页面底色（设置/短信/电话等）',
  'coui_window_background_with_card_selector.9.png': '带卡片页面的底色',
  'coui_window_bg_with_card.9.png': '卡片页面底（无状态栏版本）',
  'coui_statusbar_bg.9.png': '状态栏背景',
  'coui_list_statusbar_bg.9.png': '列表页状态栏背景',
  'coui_list_toolbar_bg.9.png': '列表页标题栏背景',
  'coui_list_preference_bg.9.png': '设置列表项背景',
  'coui_toolbar_bg.9.png': '标题栏背景',
  'coui_toolbar_largest_title_bg.9.png': '大标题页标题栏背景',
  'coui_with_card_toolbar_bg.9.png': '卡片页标题栏背景',
  'coui_tab_navigation_view_bg.9.png': '底部标签栏背景',
  'coui_tablayout_bg.9.png': '顶部 Tab 栏背景',
  'coui_searchview_corner_rect_bg.9.png': '搜索框背景',
  'common_toolbar_bg.9.png': '通用标题栏背景',
  'oplus_toolbar_bg.9.png': 'OPPO 标题栏背景',
  'toolbar_bg.9.png': '标题栏背景（通用）',
  'list_sort_item_bg.9.png': '排序弹窗条目背景',
  'systemui_panel_volume_bg.9.png': '音量调节面板底色',
  'quicksettings_slider_bg.png': '控制中心滑块轨道',
  'status_bar_qs_tile_bg_active.png': '控制中心磁贴（开启态）',
  'status_bar_qs_tile_bg_inactive.png': '控制中心磁贴（关闭态）',
  'status_bar_qs_highlighttile_bg_active.9.png': '高亮磁贴（开启态）',
  'status_bar_qs_highlighttile_bg_inactive.9.png': '高亮磁贴（关闭态）',
  'status_bar_qs_media_bg_active.png': '控制中心媒体卡片',
  'status_bar_qs_media_bg_inactive.png': '控制中心媒体卡（无播放）',
  'status_rectangle_card_bg_active.9.png': '矩形卡片（激活态）',
  'status_rectangle_card_bg_inactive.9.png': '矩形卡片（未激活）',
  'status_square_card_bg_active.png': '方形卡片（激活态）',
  'status_square_card_bg_inactive.png': '方形卡片（未激活）',
  'status_nodevice_card_bg_inactive.9.png': '无设备卡片（未激活）',
  'status_bar_qs_brightness_icon.png': '亮度图标',
  'status_bar_qs_brightness_icon_auto.png': '亮度图标（自动）',
  'status_bar_qs_icon_volume_media.png': '媒体音量图标',
  'status_bar_qs_icon_volume_media_max.png': '媒体音量图标（满）',
  'status_bar_qs_icon_volume_media_min.png': '媒体音量图标（最小）',
  'status_bar_qs_icon_volume_media_mute.png': '媒体音量图标（静音）',
  'pb_bg_dialer.9.png': '拨号盘主背景',
  'pb_bg_large_title.9.png': '拨号页大标题背景',
  'pb_bg_search_view.9.png': '拨号页搜索框背景',
  'pb_bg_another_search_view.9.png': '拨号页备用搜索框背景',
  'pb_bg_chip_group.9.png': '拨号页胶囊组背景',
  'pb_bg_chip_group_for_card.9.png': '拨号页卡片胶囊组背景',
  'pb_bg_statusbar_for_card.9.png': '拨号页状态栏（卡片式）',
  'about_device_top_video_last_frame_17.png': '关于本机顶部大图（品牌图）',
  'about_device_top_video_mask.png': '关于本机大图遮罩（配套）',
  'device_ota_card_bg_new.png': '系统更新提示卡片',
  'brand_logo.png': '品牌 Logo 蒙版（系统染色）',
  'clear_all_icon.png': '一键清理图标',
  'clear_all_bg.png': '一键清理按钮背景',
  'magic_cube_ic.png': '智慧立方体图标',
  'ic_support_tips.png': '支持提示图标',
  'ic_flip_screen_feature.png': '翻转屏幕功能图标',
  'splash.webp': '启动闪屏图',
  'splash_title_new.png': '启动闪屏标题',
  'start_slogan.9.png': '开机标语背景',
  'android12splash.png': 'Android 12 启动闪屏',
  'ic_launcher.png': '桌面图标（主）',
  'ic_launcher_foreground.png': '桌面图标前景',
  'ic_launcher_folder.png': '文件夹图标',
  'ic_foreground.png': '图标前景',
  'new_iphone_style_bg.png': '图标底板（iphone 风格）',
  'new_iphone_style_mask.png': '图标遮罩（形状蒙版）',
  'iphone_style_fg.png': '图标前景（iphone 风格）',
};

/* 无精确说明时按文件名关键词推断用途 */
function describeAsset(file) {
  if (ASSET_DESC[file]) return ASSET_DESC[file];
  const low = file.toLowerCase();
  if (/^settings_.*_ic\./.test(low)) {
    const m = { airplane: '飞行模式', bluetooh: '蓝牙', wifi: 'WiFi', brightness: '亮度',
      sound: '声音', notify: '通知', power: '电源管理', privacy: '隐私', sos: 'SOS 紧急',
      lock: '锁屏', network: '移动网络', application: '应用', account: '账号',
      about: '关于本机', cloud: '云服务', device_name: '设备名称', digital_health: '数字健康',
      general_system: '系统', google: '谷歌设置', laboratory: '实验室', more: '更多设置',
      personalise: '个性化', position: '定位', satellite: '卫星网络', special: '特色功能',
      breeno: '小布助手', wallet: '钱包', wallpaper: '壁纸' };
    for (const k in m) if (low.includes(k)) return `设置项图标：${m[k]}`;
    return '设置项图标';
  }
  if (/^stat_signal_signal_lte/.test(low)) return '状态栏 LTE 信号格';
  if (/^stat_signal_wifi/.test(low)) return '状态栏 WiFi 信号格';
  if (/^stat_signal_volte/.test(low)) return '状态栏 VoLTE 标识';
  if (/^stat_signal_activity_wifi/.test(low)) return '状态栏 WiFi 数据活动箭头';
  if (/^stat_bt_battery/.test(low)) return '蓝牙设备电量';
  if (/^stat_battery/.test(low)) return '电池图标/进度';
  if (/^stat_sys_/.test(low)) return '状态栏系统图标';
  if (/^stat_notification_/.test(low)) return '状态栏通知图标';
  if (/^icon_picacg/.test(low)) return '哔咔专属图标';
  if (low === 'nr.png') return '5G NR 标识';
  if (low === 'icon_256.png') return '应用商店图标（256px）';
  if (/signal_null/.test(low)) return '状态栏无信号图标';
  if (/kgd_.*fingerprint|fingerprint_element|osfingerprint/.test(low)) return '指纹解锁动画帧（一组连播）';
  if (/darkmode_sketch/.test(low)) return '深色模式手绘背景';
  if (/lightmode_sketch/.test(low)) return '浅色模式手绘背景';
  if (/device_ota_card_bg/.test(low)) return '系统更新卡片背景';
  if (/ic_launcher_page_point/.test(low)) return '桌面翻页指示点';
  if (/highlighttile/.test(low)) return low.includes('active') ? '高亮磁贴（开启态）' : '高亮磁贴（关闭态）';
  if (/tile_bg_unavailable/.test(low)) return '控制中心磁贴（不可用态）';
  if (/ic_shortcut_menu|ic_system_shortcut/.test(low)) return '长按快捷菜单图标';
  if (/notification_material_bg/.test(low)) return '通知卡片背景';
  if (/systemui_icon_volume_bg|systemui_panel_volume/.test(low)) return '音量调节面板底色';
  if (/status_nodevice_card/.test(low)) return '无设备卡片（未激活）';
  if (/mms_ic_contacts_avatar/.test(low)) return '短信联系人头像占位图标';
  if (/pb_ic_my_group/.test(low)) return '拨号页「我的群组」图标';
  if (/pb_ic_my_profile/.test(low)) return '拨号页「我的名片」图标';
  if (/clear_all/.test(low)) return '一键清理按钮';
  return '';
}

/* ---------------- 工具 ---------------- */
async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
  const r = await fetch(path, opt);
  const txt = await r.text();
  let data;
  try { data = JSON.parse(txt); } catch { throw new Error(txt.slice(0, 200)); }
  if (!r.ok || data.ok === false) throw new Error(data.error || '请求失败');
  return data;
}

function toast(msg, ms = 2200) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._tm);
  t._tm = setTimeout(() => t.classList.remove('show'), ms);
}

const debounce = (fn, ms = 260) => {
  let tm; return (...a) => { clearTimeout(tm); tm = setTimeout(() => fn(...a), ms); };
};

function hexToRgb(hex) {
  let h = hex.replace('#', '');
  if (h.length === 8) h = h.slice(2);
  if (h.length === 3) h = h.split('').map(c => c + c).join('');
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
  let h = 0, s = 0; const l = (mx + mn) / 2;
  if (mx !== mn) {
    const d = mx - mn;
    s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
    if (mx === r) h = (g - b) / d + (g < b ? 6 : 0);
    else if (mx === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h /= 6;
  }
  return [h * 360, s * 100, l * 100];
}
function hslToHex(h, s, l) {
  h = ((h % 360) + 360) % 360 / 360; s = Math.min(100, Math.max(0, s)) / 100; l = Math.min(100, Math.max(0, l)) / 100;
  const f = n => {
    const k = (n + h * 12) % 12;
    const a = s * Math.min(l, 1 - l);
    const c = l - a * Math.max(-1, Math.min(k - 3, Math.min(9 - k, 1)));
    return Math.round(255 * c).toString(16).padStart(2, '0');
  };
  return '#' + f(0) + f(8) + f(4);
}
const normHex = hex => {
  const [r, g, b] = hexToRgb(hex);
  return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('').toUpperCase();
};
function setAccent(hex) {
  const [r, g, b] = hexToRgb(hex);
  const [h, s, l] = rgbToHsl(r, g, b);
  const soft = hslToHex(h, Math.min(100, s * 0.85), Math.min(88, l + 22));
  const root = document.documentElement.style;
  root.setProperty('--accent', normHex(hex));
  root.setProperty('--accent-2', soft);
  root.setProperty('--accent-soft', `hsla(${h},${s}%,${l}%,.14)`);
  $('#stageSwatch').style.background = normHex(hex);
  $('#stageSwatch').style.color = normHex(hex);
  $('#stageHex').textContent = normHex(hex);
}

function fileToDataURL(file) {
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = rej;
    fr.readAsDataURL(file);
  });
}

async function uploadFile(file, { dominant = false } = {}) {
  const data = await fileToDataURL(file);
  return api('/api/upload', { data, name: file.name, dominant });
}

/* ---------------- 预览 ---------------- */
function updatePreview() {
  setAccent(S.primary);
  const homeWall = S.wallpaperUrl || (S.detail?.wallpapers?.find(w => w.role === 'home')?.url) || '';
  const lockWall = S.lockscreenUrl || homeWall;
  [['wallHome', homeWall], ['wallHomeFg', homeWall], ['wallLock', lockWall], ['wallLockFg', lockWall]]
    .forEach(([id, src]) => {
      const el = document.getElementById(id);
      if (el && el.getAttribute('src') !== (src || '')) el.src = src || '';
    });
  $('#screen').classList.toggle('fit-blur', S.wallpaperFit === 'blur');

  // 各界面背景:替换过的优先,否则用模板原资源
  const assetUrl = (f) => S.assets[f]?.url || S.detail?.key_assets?.[f] || '';
  const bindBg = (sel, file) => {
    const el = $(sel);
    if (!el) return;
    const u = assetUrl(file);
    if (el.getAttribute('src') !== u) el.src = u;
  };
  bindBg('#setBg', 'coui_window_background_selector.9.png');
  bindBg('#smsBg', 'coui_window_background_selector.9.png');
  bindBg('#dialBg', 'pb_bg_dialer.9.png');
  bindBg('#aboutImg', 'about_device_top_video_last_frame_17.png');
  bindBg('#aboutBg', 'about_device_top_video_last_frame_17.png');
  bindBg('#volBg', 'systemui_panel_volume_bg.9.png');

  const tip = (sel, file, label) => {
    const el = $(sel);
    if (!el) return;
    if (S.assets[file]) el.textContent = `${label}：已替换`;
    else if (S.detail?.key_assets?.[file]) el.textContent = `${label}：模板原图`;
    else el.textContent = `${label}：模板未包含`;
  };
  tip('#setTip', 'coui_window_background_selector.9.png', '设置背景');
  tip('#smsTip', 'coui_window_background_selector.9.png', '短信背景');
  tip('#dialTip', 'pb_bg_dialer.9.png', '拨号背景');
  tip('#aboutTip', 'about_device_top_video_last_frame_17.png', '关于本机大图');

  $$('.page').forEach(p => p.classList.toggle('show', p.dataset.page === S.view));
  $('#screen').dataset.view = S.view;
  $$('#viewSeg button').forEach(b => b.classList.toggle('on', b.dataset.view === S.view));
  const activeTab = $(`#viewSeg button[data-view="${S.view}"]`);
  if (activeTab) activeTab.scrollIntoView({ block: 'nearest', inline: 'center' });

  // 配色走向
  const sw = S.swatches.length ? S.swatches.slice(0, 8) : [];
  $('#stageRamp').innerHTML = sw.length
    ? sw.map(s => `<i style="background:${s.out}"></i>`).join('')
    : '<i style="background:#1c2230"></i>'.repeat(5);
}

function renderIconPreview() {
  const grid = $('#iconGrid');
  if (!grid) return;
  const dock = $('#dockGrid');
  if (!S.detail) {
    grid.innerHTML = Array.from({ length: 12 }, (_, i) =>
      `<div class="app"><div class="ic" style="background:linear-gradient(140deg,var(--accent),rgba(255,255,255,.25))"></div><div class="nm">应用 ${i + 1}</div></div>`).join('');
    if (dock) dock.innerHTML = '';
    return;
  }
  const list = S.detail.icons.filter(i => !i.system && i.packages.length).slice(0, 16);
  const cell = (ic) => {
    const ch = S.icons[ic.file];
    const url = ch ? ch.url : ic.url;
    const label = appName(ic.packages[0]);
    return `<div class="app"><div class="ic"><img src="${url}" alt=""></div><div class="nm">${label}</div></div>`;
  };
  grid.innerHTML = list.slice(0, 12).map(i => cell(i)).join('');
  if (dock) dock.innerHTML = list.slice(12, 16).map(i => cell(i)).join('');
}

/* ---------------- 模板 ---------------- */
async function loadTemplates() {
  const r = await api('/api/templates');
  S.templates = r.templates;
  if (S.step === 'template') renderPanel();
}

async function selectTemplate(id) {
  try {
    S.busy = true;
    const d = await api('/api/template/load', { id });
    S.tpl = id;
    S.detail = d;
    try { localStorage.setItem(TPL_KEY, id); } catch { /* 隐私模式 */ }
    S.primary = S.urlPrimary || d.palette.anchor;
    S.anchor = d.palette.anchor;
    S.swatches = d.palette.swatches;
    S.overrides = {};
    S.icons = {};
    S.iconRemoved = [];
    S.assets = {};
    S.previews = {};
    S.previewRemoved = [];
    S.assetData = null;
    S.wallpaper = S.lockscreen = null;
    S.wallpaperUrl = S.lockscreenUrl = null;
    S.name = S.urlName || d.info.summary || '我的主题';
    S.author = d.info.author || '';
    S.description = d.info.description || '';
    S.uuid = '';
    S.isGlobal = d.info.is_global !== '0';
    $('#tplPill').textContent = d.info.summary || '未命名主题';
    $('#pkgPill').textContent = `${d.packages.length} 个子包 · ${d.icons.length} 个图标`;
    $('#railName').textContent = d.info.summary || '未命名主题';
    $('#railAuthor').textContent = d.info.author || '未知作者';
    const cover = d.previews.find(p => p.key === 'menu') || d.previews[0];
    if (cover) {
      $('#railThumb').style.backgroundImage = `url("${cover.url}")`;
      $('#railThumb').textContent = '';
    }
    $('#tplPreviews').innerHTML = d.previews.map(p =>
      `<img src="${p.url}" data-full="${p.url}" title="${p.key}">`).join('');
    $$('#tplPreviews img').forEach(img => img.onclick = () =>
      showModal(`<img src="${img.dataset.full}">`));
    markSteps();
    updatePreview();
    renderIconPreview();
    await fetchPalette();
    S.busy = false;
    S.step = S.hashStep || 'color';
    renderPanel();
    toast('模板已载入：' + (d.info.summary || ''));
  } catch (e) {
    console.error(e);
    toast('载入失败：' + e.message, 3200);
  } finally {
    S.busy = false;
  }
}

async function fetchPalette() {
  if (!S.tpl) return;
  try {
    const r = await api('/api/palette', {
      tpl: S.tpl, primary: S.primary, anchor: S.anchor,
      strength: S.strength, hue_only: S.hueOnly,
      protect_neutrals: S.protect, tint_light: S.tintLight,
      recolor: S.recolor, overrides: S.overrides,
    });
    S.swatches = r.swatches;
    updatePreview();
    if (S.step === 'color') {
      renderSwatches();
      const em = $('#swatchGrid')?.closest('.p-sec')?.querySelector('h3 em');
      if (em) {
        const n = S.swatches.filter(s => !s.neutral).reduce((a, s) => a + s.count, 0);
        em.textContent = `上=原色 下=新色 · 影响 ${n} 处`;
      }
    }
  } catch (e) {
    console.warn('配色预览失败', e);
  }
}

const refreshPalette = debounce(fetchPalette, 240);

function renderSwatches() {
  const grid = $('#swatchGrid');
  if (!grid) return;
  const list = S.swatches
    .map((s, i) => ({ ...s, i, out: s.out || s.rgb }))
    .filter(s => !s.neutral || s.out !== s.rgb)
    .slice(0, 12);
  grid.innerHTML = list.map(s => {
    const ov = !!S.overrides[s.hex];
    const customHex = ov ? S.overrides[s.hex].replace('#', '') : s.out.replace('#', '');
    return `<div class="swatch ${ov ? 'locked' : ''}" data-i="${s.i}" data-hex="${s.hex}" title="原色 ${s.hex} · 出现 ${s.count} 次${ov ? ' · 已自定义' : ' · 点击自定义改色'}">
      <div class="half" style="background:${s.rgb}"></div>
      <div class="half" style="background:${ov ? '#' + customHex : s.out};outline:${ov ? '1px solid #fff' : 'none'};outline-offset:-1px"></div>
      <span class="cnt">${s.count}</span>
      <small>${customHex}</small>
      ${ov ? '<b class="lock">✎</b>' : ''}
    </div>`;
  }).join('') || '<div class="hint" style="grid-column:1/-1">这套模板的颜色都很中性，改主色不会影响它们。可以打开「浅色也染色」。</div>';
  $$('.swatch', grid).forEach(el => el.onclick = () => {
    editSwatch(el.dataset.hex, el.dataset.i);
  });
}

// 弹出自定义改色：用户直接选/填任意颜色
function editSwatch(hex, i) {
  const s = S.swatches[+i];
  if (!s) return;
  const cur = (S.overrides[hex] || s.out).replace('#', '');
  openColorModal({
    title: '自定义「' + hex + '」的颜色',
    init: '#' + cur,
    onPick: (c) => {
      S.overrides[hex] = c;          // 记录：原色 -> 自定义色
      S.manual = S.manual || {};     // 标记进入手动模式
      refreshPalette();
      toast('已自定义 ' + hex + ' → ' + c);
    },
    onClear: () => {
      delete S.overrides[hex];
      refreshPalette();
      toast('已还原 ' + hex + ' 为自动配色');
    },
  });
}

/* ---------------- 面板 ---------------- */
function markSteps() {
  $$('.step').forEach(b => {
    b.classList.toggle('on', b.dataset.step === S.step);
    b.classList.toggle('done', !!S.tpl && b.dataset.step !== S.step);
  });
}

function renderPanel() {
  markSteps();
  const p = $('#panel');
  const fns = {
    template: panelTemplate, color: panelColor, wallpaper: panelWallpaper,
    icons: panelIcons, assets: panelAssets, meta: panelMeta,
  };
  p.innerHTML = (fns[S.step] || panelTemplate)();
  bindPanel();
  if (S.step === 'color') { renderSwatches(); }
  if (S.step === 'icons') renderIconGrid();
  if (S.step === 'assets') { ensureAssets(); renderAssets(); }
  if (S.step === 'meta') loadOutputs();
}

function panelTemplate() {
  if (!S.templates.length) {
    return `<div class="p-head"><h2>选择模板</h2>
      <p>先导入一个可用的 ColorOS 17 主题作为骨架，工坊会解析它的配色表、壁纸与图标清单。</p></div>
      <button class="btn wide primary" data-act="import">导入 .theme 文件</button>
      <div class="empty"><b>模板库为空</b>把你手上的 ColorOS 17 主题（.theme）拖进来即可开始</div>`;
  }
  return `<div class="p-head"><h2>选择模板</h2>
    <p>模板即"骨架"。所有改动都在它的资源结构上完成，保证打包后与 ColorOS 17 完全兼容。</p></div>
    <div class="tpl-list">
      ${S.templates.map(t => `
        <div class="tpl-item ${t.id === S.tpl ? 'on' : ''}" data-id="${t.id}">
          <div class="tpl-cover" style="${t.cover ? `background-image:url('${t.cover}')` : ''}"></div>
          <div class="tpl-info">
            <strong>${esc(t.info.summary || t.file)}</strong>
            <small>${esc(t.info.author || '未知作者')}</small>
            <div class="tags">
              <span class="tag">${t.packages || '?'} 包</span>
              <span class="tag">${(t.size / 1048576).toFixed(1)} MB</span>
            </div>
          </div>
          <button class="tpl-del" data-del="${t.id}" title="移除">×</button>
        </div>`).join('')}
    </div>
    <div style="margin-top:14px"><button class="btn wide" data-act="import">＋ 导入新的 .theme</button></div>`;
}

function panelColor() {
  if (!S.detail) return needTemplate('配色方案');
  const anchor = S.anchor;
  const affected = S.swatches.filter(s => !s.neutral).reduce((n, s) => n + s.count, 0);
  return `<div class="p-head"><h2>配色方案</h2>
    <p>模板主色为 <code style="color:var(--accent-2)">${anchor}</code>，把它换成你的颜色，整套系统的明暗层次会自动跟着走。</p></div>

    <div class="p-sec">
      <h3>主题主色</h3>
      <div class="presets">
        ${PRESETS.map(p => `<button class="preset ${'#' + p.slice(3) === toSimpleHex(S.primary) ? 'on' : ''}" data-color="${p}" style="background:${p}"></button>`).join('')}
      </div>
      <div class="color-row">
        <input type="color" id="colorPick" value="${toSimpleHex(S.primary)}">
        <input class="input" id="colorHex" value="${toSimpleHex(S.primary)}" maxlength="9" spellcheck="false">
        <button class="btn" data-act="fromWall" title="从壁纸提取主色">取色</button>
      </div>
      <div class="hint">「取色」会从当前壁纸里提取最有代表性的颜色</div>
      <div style="margin-top:9px"><button class="btn" data-act="resetColor" style="height:30px;font-size:12px">还原为模板原配色</button></div>
    </div>

    <div class="p-sec">
      <h3>变换强度 <em>${Math.round(S.strength * 100)}%</em></h3>
      <div class="slider-row">
        <input type="range" id="strength" min="0" max="150" value="${Math.round(S.strength * 100)}">
      </div>
      <div class="hint">100% 为主色精确替换；降低可保留更多模板原色</div>
    </div>

    <div class="p-sec">
      <h3>精细控制</h3>
      <div class="switch-row ${S.hueOnly ? 'on' : ''}" data-toggle="hueOnly">
        <div><span>仅旋转色相</span><small>饱和度与明度完全保持模板原样</small></div><div class="sw"></div>
      </div>
      <div class="switch-row ${S.protect ? 'on' : ''}" data-toggle="protect">
        <div><span>保护灰阶</span><small>黑、白、灰不被染色（推荐）</small></div><div class="sw"></div>
      </div>
      <div class="switch-row ${S.tintLight ? 'on' : ''}" data-toggle="tintLight">
        <div><span>浅色也染色</span><small>白灰系主题专用，给白底铺一层淡主题色</small></div><div class="sw"></div>
      </div>
    </div>

    <div class="p-sec">
      <h3>色板映射 <em>上=原色 下=新色 · 影响 ${affected} 处</em></h3>
      <div class="swatch-grid" id="swatchGrid"></div>
      <div class="hint">点任意色块，手动指定该原色要变成什么颜色（任意值，不受主色算法约束）；带 ✎ 标记的是已自定义，再点可改或清除。</div>
      <div style="margin-top:9px"><button class="btn wide" data-act="clearOverrides" style="height:30px;font-size:12px">清除全部自定义，回到自动配色</button></div>
    </div>`;
}

function panelWallpaper() {
  if (!S.detail) return needTemplate('壁纸');
  const home = S.detail.wallpapers.find(w => w.role === 'home');
  const lock = S.detail.wallpapers.find(w => w.role === 'lock');
  return `<div class="p-head"><h2>壁纸</h2>
    <p>原图任意尺寸都可以，会自动按模板的分辨率等比裁剪并压缩。</p></div>

    <div class="p-sec">
      <h3>填充方式</h3>
      <div class="presets" id="fitRow">
        ${[['cover', '裁剪铺满'], ['blur', '完整显示 · 模糊补边']].map(([v, n]) =>
      `<button class="btn ${S.wallpaperFit === v ? 'primary' : ''}" data-fit="${v}" style="height:32px;padding:0 14px;font-size:12px">${n}</button>`).join('')}
      </div>
      <div class="hint">非竖屏比例的图片建议用「模糊补边」，不会被裁掉主体</div>
    </div>

    <div class="p-sec">
      <h3>桌面壁纸 ${home ? `<em>${home.w}×${home.h}</em>` : ''}</h3>
      <div class="drop" data-drop="home" id="dropHome">
        ${S.wallpaperUrl ? `<img src="${S.wallpaperUrl}">` : (home ? `<img src="${home.url}">` : '')}
        <b>${S.wallpaperUrl ? '已更换 · 点击重新选择' : '点击或拖入图片'}</b>
        <small>建议竖图，长宽比接近 9:20</small>
      </div>
    </div>

    <div class="p-sec">
      <h3>锁屏壁纸 ${lock ? `<em>${lock.w}×${lock.h}</em>` : ''}</h3>
      <div class="drop" data-drop="lock" id="dropLock">
        ${S.lockscreenUrl ? `<img src="${S.lockscreenUrl}">` : (lock ? `<img src="${lock.url}">` : '')}
        <b>${S.lockscreenUrl ? '已更换 · 点击重新选择' : '点击或拖入图片'}</b>
        <small>留空则与桌面壁纸共用</small>
      </div>
      ${S.wallpaperUrl || S.lockscreenUrl ? '<div style="margin-top:9px"><button class="btn wide" data-act="resetWall">恢复模板壁纸</button></div>' : ''}
    </div>`;
}

function panelIcons() {
  if (!S.detail) return needTemplate('图标');
  const changed = Object.keys(S.icons).length;
  const added = Object.values(S.icons).filter(v => v.isNew).length;
  const replaced = changed - added;
  const removed = S.iconRemoved.length;
  const size = S.detail.icons[0] ? `${S.detail.icons[0].w}×${S.detail.icons[0].h}` : '168×168';
  return `<div class="p-head"><h2>图标</h2>
    <p>模板共 ${S.detail.icons.length} 个图标，规格 <b style="color:var(--accent-2)">${size}</b>。
    文件名用应用包名（如 <code>com.alicloud.databox.png</code>）就能批量导入并自动对应。</p></div>

    <div class="p-sec">
      <h3>批量导入 <em>文件名 = 包名.png</em></h3>
      <button class="btn wide primary" data-act="importIcons">选择一批图标（可多选）</button>
      <div class="hint">支持任意数量，自动识别包名：模板里已有的直接替换，没有的自动新增并写入桌面映射。也可以把文件夹拖进来。</div>
    </div>

    <div class="p-sec">
      <h3>图标形状</h3>
      <div class="presets" id="shapeRow">
        ${[['', '原样'], ['squircle', '超椭圆'], ['rounded', '圆角'], ['circle', '圆形'], ['square', '方形']]
      .map(([v, n]) => `<button class="btn ${S.iconShape === v ? 'primary' : ''}" data-shape="${v}" style="height:32px;padding:0 12px;font-size:12px">${n}</button>`).join('')}
      </div>
      <div class="hint">形状通过替换桌面包的蒙版实现，部分机型需重启桌面生效</div>
    </div>

    <div class="p-sec">
      <h3>图标缩放 <em>${S.iconScale ? S.iconScale.toFixed(2) : '默认'}</em></h3>
      <div class="slider-row">
        <input type="range" id="iconScale" min="0" max="90" value="${Math.round(S.iconScale * 100)}">
      </div>
    </div>

    <div class="p-sec">
      <h3>图标列表
        <em>${replaced ? `替换 ${replaced}` : ''}${added ? ` · 新增 ${added}` : ''}${removed ? ` · 移除 ${removed}` : ''}${!changed && !removed ? '未修改' : ''}</em>
      </h3>
      <div class="icon-tools">
        <input class="input" id="iconSearch" placeholder="搜索应用名或包名" value="${esc(S.iconQuery)}" style="height:34px">
        <button class="btn" data-act="addIcon" title="单个新增">＋ 单个</button>
      </div>
      <div class="icon-grid" id="iconGridPanel"></div>
      <div class="hint">点图标替换 · 右上角 × 移除 · 左下角 ↺ 撤销</div>
    </div>

    <div class="p-sec">
      <h3>状态栏</h3>
      <div class="switch-row ${S.tint ? 'on' : ''}" data-toggle="tint">
        <div><span>状态栏图标着色</span><small>把系统图标刷成主题色（谨慎使用）</small></div><div class="sw"></div>
      </div>
    </div>`;
}

function panelAssets() {
  if (!S.detail) return needTemplate('界面资源');
  const d = S.assetData;
  const changed = Object.keys(S.assets).length;

  const quick = QUICK_ASSETS.map(q => {
    const hit = d?.assets.find(a => a.file === q.file);
    const done = !!S.assets[q.file];
    if (!hit) {
      return `<button class="quick off" disabled>
        <span class="q-thumb"></span>
        <b>${q.name}</b><small>模板未包含</small></button>`;
    }
    return `<button class="quick ${done ? 'done' : ''}" data-file="${esc(q.file)}" title="${esc(q.note)} · ${hit.w}×${hit.h}">
      <span class="q-thumb"><img src="${S.assets[q.file]?.url || hit.url}" alt=""></span>
      <b>${q.name}</b>
      <small>${hit.w}×${hit.h}${hit.copies > 1 ? ` · ${hit.copies} 包` : ''}${done ? ' · 已换' : ''}</small>
    </button>`;
  }).join('');

  const pkgs = d?.packages || [];

  return `<div class="p-head"><h2>界面资源</h2>
    <p>系统界面里的图片：设置背景、音量面板、关于本机动画帧、Logo……
    点任意一张即可替换，尺寸会自动对齐原资源。</p></div>

    <div class="p-sec">
      <h3>商店预览图 <em>增删改 · 商店里展示的就是这几张</em></h3>
      ${previewSection()}
      <div class="hint">模板自带的是原作者做的效果图，建议换成你自己的；删掉的图不会写进包里</div>
    </div>

    <div class="p-sec">
      <h3>常用位置 <em>${changed ? `已改 ${changed}` : '点图替换'}</em></h3>
      <div class="quick-grid">${quick}</div>
    </div>

    <div class="p-sec">
      <h3>处理方式</h3>
      <div class="presets">
        ${[['cover', '裁剪铺满'], ['contain', '完整显示']].map(([v, n]) =>
    `<button class="btn ${S.assetFit === v ? 'primary' : ''}" data-afit="${v}" style="height:30px;padding:0 12px;font-size:12px">${n}</button>`).join('')}
      </div>
      <div class="switch-row ${S.assetCompress ? 'on' : ''}" data-toggle="compress" style="margin-top:9px">
        <div><span>大图压缩</span><small>背景这类大图降到 256 色，包体可小一半</small></div><div class="sw"></div>
      </div>
    </div>

    <div class="p-sec">
      <h3>全部资源 <em>${d ? `${d.total} 张` : '加载中…'}</em></h3>
      <div class="icon-tools">
        <input class="input" id="assetSearch" placeholder="搜索文件名…" value="${esc(S.assetFilter)}" style="height:34px">
      </div>
      <div class="icon-tools" style="margin-top:-2px">
        <div class="dd" id="assetCat" style="flex:1">
          <button class="dd-btn" type="button" data-dd="assetCat">
            <span class="dd-val">${S.assetCat ? (ASSET_CATS.find(c => c.key === S.assetCat)?.icon + ' ' + ASSET_CATS.find(c => c.key === S.assetCat)?.name) : '全部分类'}</span>
            <span class="dd-arrow">▾</span>
          </button>
          <div class="dd-menu">
            <div class="dd-item ${!S.assetCat ? 'on' : ''}" data-dd="assetCat" data-val="">全部分类</div>
            ${ASSET_CATS.map(c => `<div class="dd-item ${S.assetCat === c.key ? 'on' : ''}" data-dd="assetCat" data-val="${c.key}">${c.icon} ${c.name}</div>`).join('')}
          </div>
        </div>
        <div class="dd" id="assetPkg" style="flex:1">
          <button class="dd-btn" type="button" data-dd="assetPkg">
            <span class="dd-val">${S.assetPkg ? esc(S.assetPkg) : '全部包'}</span>
            <span class="dd-arrow">▾</span>
          </button>
          <div class="dd-menu">
            <div class="dd-item ${!S.assetPkg ? 'on' : ''}" data-dd="assetPkg" data-val="">全部包</div>
            ${pkgs.map(p => `<div class="dd-item ${S.assetPkg === p.base ? 'on' : ''}" data-dd="assetPkg" data-val="${esc(p.base)}">${esc(p.base)} (${p.count})</div>`).join('')}
          </div>
        </div>
      </div>
      <div class="asset-list" id="assetList">
        ${d ? '' : '<div class="hint">正在读取资源…</div>'}
      </div>
      <div class="hint">每张图都标了用途，按分类或包名筛选；同名资源（如设置背景在 5 个包里各一份）会自动联动替换</div>
    </div>`;
}

function ensureAssets() {
  if (S.assetData || !S.tpl) return;
  api('/api/assets?tpl=' + encodeURIComponent(S.tpl))
    .then(d => {
      S.assetData = d;
      if (S.step === 'assets') { renderPanel(); }
    })
    .catch(e => toast('资源读取失败：' + e.message, 3200));
}

function renderAssets() {
  const box = $('#assetList');
  if (!box || !S.assetData) return;
  const q = S.assetFilter.toLowerCase();
  let list = S.assetData.assets.filter(a => (!S.assetPkg || a.base === S.assetPkg));
  if (S.assetCat) list = list.filter(a => assetCat(a.file) === S.assetCat);
  if (q) list = list.filter(a => a.file.toLowerCase().includes(q) || a.base.includes(q));

  // 同名资源只显示一条（替换时本来就联动所有副本）
  const seen = new Set();
  list = list.filter(a => (seen.has(a.file) ? false : (seen.add(a.file), true)));

  // 按分类排序，同分类内按文件名
  list.sort((x, y) => {
    const cx = CAT_ORDER.indexOf(assetCat(x.file)), cy = CAT_ORDER.indexOf(assetCat(y.file));
    return (cx - cy) || x.file.localeCompare(y.file);
  });

  if (!list.length) {
    box.innerHTML = '<div class="hint">没有匹配的资源</div>';
    return;
  }
  const MAX = 150;
  box.innerHTML = list.slice(0, MAX).map(a => {
    const done = S.assets[a.file];
    const cat = assetCat(a.file);
    const catInfo = ASSET_CATS.find(c => c.key === cat);
    const desc = describeAsset(a.file);
    return `<div class="asset-cell ${done ? 'done' : ''}" data-file="${esc(a.file)}" data-pkg="${esc(a.pkg)}"
        title="${esc(a.pkg)}/${esc(a.path)}&#10;${esc(desc || a.file)}&#10;点击替换">
      <span class="a-thumb"><img loading="lazy" src="${done ? done.url : a.url}" alt=""></span>
      <span class="a-meta">
        <b>${esc(a.file)}</b>
        ${desc ? `<em class="a-desc">${esc(desc)}</em>` : ''}
        <small>${a.w}×${a.h} · ${a.kb}KB${a.copies > 1 ? ` · 联动 ${a.copies} 个包` : ''}</small>
      </span>
      <i class="a-cat cat-${cat}">${catInfo.icon} ${catInfo.name}</i>
      ${a.nine ? '<i class="a-flag">.9</i>' : ''}
      ${done ? `<i class="a-done">已改</i><i class="a-reset" data-reset="${esc(a.file)}" title="还原为模板原图">↺</i>` : ''}
    </div>`;
  }).join('') + (list.length > MAX
    ? `<div class="hint" style="grid-column:1/-1">还有 ${list.length - MAX} 张，用搜索或选择具体分类/包查看</div>` : '');
}

function panelMeta() {
  if (!S.detail) return needTemplate('主题信息');
  return `<div class="p-head"><h2>主题信息与导出</h2>
    <p>写入 themeInfo.xml，安装后在主题商店里显示的就是这些内容。</p></div>

    <div class="p-sec">
      <div class="field"><label>主题名称</label>
        <input class="input" data-bind="name" value="${esc(S.name)}" placeholder="例如：樱花未来"></div>
      <div class="field"><label>作者</label>
        <input class="input" data-bind="author" value="${esc(S.author)}" placeholder="你的昵称"></div>
      <div class="field"><label>描述</label>
        <textarea class="input" data-bind="description" placeholder="适配说明、素材来源、使用条款…">${esc(S.description)}</textarea></div>
      <div class="field" style="display:flex;gap:9px">
        <div style="flex:1"><label>版本名</label><input class="input" data-bind="versionName" value="${esc(S.versionName)}"></div>
        <div style="width:92px"><label>版本号</label><input class="input" data-bind="versionCode" value="${S.versionCode}"></div>
      </div>
      <div class="field"><label>UUID（留空则自动生成）</label>
        <input class="input" data-bind="uuid" value="${esc(S.uuid)}" placeholder="32 位十六进制，留空自动生成" style="font-family:Consolas,monospace;font-size:11.5px">
        <div style="margin-top:7px"><button class="btn" data-act="newUuid" style="height:30px;font-size:12px">随机生成新 UUID</button></div>
      </div>
    </div>

    <div class="p-sec">
      <h3>应用范围</h3>
      <div class="switch-row ${S.isGlobal ? 'on' : ''}" data-toggle="global">
        <div><span>全局主题</span><small>壁纸、图标、配色整体应用到系统各界面（IsGlobalTheme=1）</small></div><div class="sw"></div>
      </div>
      <div class="hint">关闭后只在主题商店里作为局部主题存在，桌面/状态栏可能不生效</div>
    </div>

    <div class="p-sec">
      <button class="btn wide primary" data-act="build" ${S.busy ? 'disabled' : ''}>
        ${S.busy ? '正在打包…' : '生成 .theme 主题包'}
      </button>
      <div class="hint">生成后会保存在 output 目录，同时提供下载</div>
    </div>

    <div id="resultBox">${renderResult()}</div>

    <div class="p-sec" style="margin-top:18px">
      <h3>历史输出</h3>
      <div id="outputList"><div class="hint">加载中…</div></div>
    </div>

    <div class="p-sec">
      <h3>安装到手机</h3>
      <div class="hint" style="line-height:1.9">
        1. 把 .theme 传到手机（数据线 / 微信文件传输助手）<br>
        2. 用「文件管理」打开它，选择「主题商店」导入<br>
        3. 打开主题商店 → 我的 → 主题 → 应用<br>
        4. 若提示未通过审核，部分机型需在主题商店设置里关闭「主题安全校验」
      </div>
    </div>`;
}

function needTemplate(title) {
  return `<div class="p-head"><h2>${title}</h2><p>还没有载入模板。</p></div>
    <div class="empty"><b>请先选择一个模板</b>模板决定了配色表位置、壁纸槽位与图标清单</div>
    <button class="btn wide primary" data-act="gotoTemplate">去选择模板</button>`;
}

function renderResult() {
  const r = S.lastResult;
  if (!r) return '';
  if (r.error) {
    return `<div class="result err"><b>生成失败</b><small>${esc(r.error)}</small></div>`;
  }
  return `<div class="result">
    <b>已生成 · ${(r.size / 1048576).toFixed(2)} MB</b>
    <small>耗时 ${r.elapsed}s · ${r.filename}</small>
    ${r.warnings?.length ? `<div class="log" style="color:#ffb86b">⚠ ${r.warnings.map(esc).join('\n⚠ ')}</div>` : ''}
    <div class="log">${(r.log || []).map(esc).join('\n')}</div>
    <a class="btn wide primary" style="display:grid;place-items:center;margin-top:10px;text-decoration:none" href="${r.download}">下载 .theme</a>
  </div>`;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
const toSimpleHex = h => {
  const n = normHex(h);
  return n.length === 7 ? n : '#' + n.slice(3);
};

/* ---------------- 面板事件 ---------------- */
function bindPanel() {
  const p = $('#panel');

  $$('.tpl-item', p).forEach(el => {
    el.onclick = e => {
      if (e.target.closest('[data-del]')) return;
      selectTemplate(el.dataset.id);
    };
  });
  $$('[data-del]', p).forEach(b => {
    b.onclick = async e => {
      e.stopPropagation();
      if (!confirm('从模板库移除这个主题？源文件会被删除')) return;
      await api('/api/template/delete', { id: b.dataset.del });
      if (S.tpl === b.dataset.del) { S.tpl = null; S.detail = null; }
      await loadTemplates();
      toast('已移除');
    };
  });

  $$('[data-act]', p).forEach(b => {
    const act = b.dataset.act;
    b.onclick = async () => {
      if (act === 'import') pickFile('theme', 1);
      if (act === 'gotoTemplate') { S.step = 'template'; renderPanel(); }
      if (act === 'build') doBuild();
      if (act === 'newUuid') {
        S.uuid = randomUuid();
        const inp = $('[data-bind="uuid"]');
        if (inp) inp.value = S.uuid;
        toast('已生成新 UUID');
      }
      if (act === 'resetWall') {
        S.wallpaper = S.lockscreen = null;
        S.wallpaperUrl = S.lockscreenUrl = null;
        updatePreview(); renderPanel();
      }
      if (act === 'batchIcons' || act === 'importIcons') pickFile('icons', 0);
      if (act === 'addPreview') {
        const used = new Set(Object.keys(S.previews));
        let n = 1;
        while (used.has('extra' + n)) n++;
        pickFile('preview', 1, 'extra' + n);
      }
      if (act === 'addIcon') openAddIcon();
      if (act === 'fromWall') pickFromWall();
      if (act === 'resetColor') {
        S.overrides = {};
        setPrimary(S.anchor);
        renderPanel();
        toast('已还原模板配色');
      }
      if (act === 'clearOverrides') {
        S.overrides = {};
        refreshPalette();
        toast('已清除全部自定义颜色');
      }
    };
  });

  $$('[data-toggle]', p).forEach(el => {
    el.onclick = () => {
      const k = el.dataset.toggle;
      if (k === 'hueOnly') S.hueOnly = !S.hueOnly;
      if (k === 'protect') S.protect = !S.protect;
      if (k === 'tintLight') S.tintLight = !S.tintLight;
      if (k === 'tint') S.tint = !S.tint;
      if (k === 'compress') S.assetCompress = !S.assetCompress;
      if (k === 'global') S.isGlobal = !S.isGlobal;
      el.classList.toggle('on');
      if (['hueOnly', 'protect', 'tintLight'].includes(k)) refreshPalette();
    };
  });

  // —— 界面资源 ——
  $$('.quick, .asset-cell', p).forEach(el => {
    el.onclick = e => {
      if (e.target.closest('[data-reset]')) return;
      if (el.dataset.file) pickFile('asset', 1, el.dataset.file);
    };
  });
  $$('[data-reset]', p).forEach(b => {
    b.onclick = e => {
      e.stopPropagation();
      delete S.assets[b.dataset.reset];
      renderPanel();
      toast('已还原 ' + b.dataset.reset);
    };
  });
  $$('[data-afit]', p).forEach(b => {
    b.onclick = () => { S.assetFit = b.dataset.afit; renderPanel(); };
  });
  $$('.pv-card', p).forEach(el => {
    el.onclick = e => {
      const del = e.target.closest('[data-pvdel]');
      if (del) {
        e.stopPropagation();
        previewDelete(del.dataset.pvdel);
        return;
      }
      pickFile('preview', 1, el.dataset.preview);
    };
  });
  const asr = $('#assetSearch');
  if (asr) asr.oninput = () => { S.assetFilter = asr.value.trim(); renderAssets(); };
  // 自定义下拉
  $$('.dd-btn', p).forEach(btn => btn.onclick = (e) => {
    e.stopPropagation();
    const dd = btn.closest('.dd');
    const wasOpen = dd.classList.contains('open');
    $$('.dd.open', p).forEach(x => x.classList.remove('open'));
    if (!wasOpen) dd.classList.add('open');
  });
  $$('.dd-item', p).forEach(it => it.onclick = (e) => {
    e.stopPropagation();
    const key = it.dataset.dd, val = it.dataset.val;
    if (key === 'assetCat') S.assetCat = val;
    if (key === 'assetPkg') S.assetPkg = val;
    it.closest('.dd').classList.remove('open');
    renderPanel();  // 重渲染，更新按钮显示
  });
  // 点击别处关闭下拉
  document.addEventListener('click', () => $$('.dd.open', p).forEach(x => x.classList.remove('open')));

  $$('[data-color]', p).forEach(b => {
    b.onclick = () => { setPrimary(b.dataset.color); };
  });

  const cp = $('#colorPick');
  if (cp) cp.oninput = () => setPrimary(cp.value, true);
  const hx = $('#colorHex');
  if (hx) {
    hx.onchange = () => {
      const v = hx.value.trim();
      if (/^#?[0-9a-fA-F]{6,8}$/.test(v)) setPrimary(v.startsWith('#') ? v : '#' + v);
      else toast('颜色格式不对');
    };
  }

  const st = $('#strength');
  if (st) {
    st.oninput = () => {
      S.strength = +st.value / 100;
      const em = st.closest('.p-sec').querySelector('h3 em');
      if (em) em.textContent = Math.round(S.strength * 100) + '%';
      refreshPalette();
    };
  }

  const isc = $('#iconScale');
  if (isc) {
    isc.oninput = () => {
      S.iconScale = +isc.value / 100;
      const em = isc.closest('.p-sec').querySelector('h3 em');
      if (em) em.textContent = S.iconScale ? S.iconScale.toFixed(2) : '默认';
    };
  }

  $$('[data-shape]', p).forEach(b => {
    b.onclick = () => { S.iconShape = b.dataset.shape; renderPanel(); };
  });

  $$('[data-fit]', p).forEach(b => {
    b.onclick = () => { S.wallpaperFit = b.dataset.fit; updatePreview(); renderPanel(); };
  });

  const isr = $('#iconSearch');
  if (isr) isr.oninput = () => { S.iconQuery = isr.value.trim(); renderIconGrid(); };

  // 图标网格用事件委托（卡片是动态渲染的）
  const ig = $('#iconGridPanel');
  if (ig) {
    ig.onclick = e => {
      const del = e.target.closest('[data-del]');
      if (del) { e.stopPropagation(); iconToggleDelete(del.dataset.del); return; }
      const undo = e.target.closest('[data-undo]');
      if (undo) {
        e.stopPropagation();
        delete S.icons[undo.dataset.undo];
        renderPanel();
        toast('已撤销 ' + undo.dataset.undo);
        return;
      }
      const cell = e.target.closest('.icon-cell');
      if (cell) pickFile('icon', 1, cell.dataset.file);
    };
  }

  // 资源列表同样用委托
  const al = $('#assetList');
  if (al) {
    al.onclick = e => {
      if (e.target.closest('[data-reset]')) return;
      const cell = e.target.closest('.asset-cell');
      if (cell && cell.dataset.file) pickFile('asset', 1, cell.dataset.file);
    };
  }

  $$('[data-drop]', p).forEach(el => {
    const role = el.dataset.drop;
    el.onclick = () => pickFile('wallpaper', 1, role);
    el.ondragover = e => { e.preventDefault(); el.classList.add('over'); };
    el.ondragleave = () => el.classList.remove('over');
    el.ondrop = e => {
      e.preventDefault(); el.classList.remove('over');
      const f = e.dataTransfer.files[0];
      if (f) applyWallpaper(f, role);
    };
  });

  $$('[data-bind]', p).forEach(inp => {
    inp.oninput = () => {
      const k = inp.dataset.bind;
      S[k] = k === 'versionCode' ? (parseInt(inp.value) || 1) : inp.value;
    };
  });
}

function setPrimary(hex, fromPicker = false) {
  S.primary = normHex(hex).length === 7 ? '#FF' + normHex(hex).slice(1) : normHex(hex);
  setAccent(S.primary);
  const cp = $('#colorPick'), hx = $('#colorHex');
  if (cp && !fromPicker) cp.value = toSimpleHex(S.primary);
  if (hx) hx.value = toSimpleHex(S.primary);
  $$('[data-color]').forEach(b => b.classList.toggle('on', b.dataset.color === S.primary));
  refreshPalette();
}

function renderIconGrid() {
  const box = $('#iconGridPanel');
  if (!box || !S.detail) return;
  const q = S.iconQuery.toLowerCase().trim();

  const items = S.detail.icons.map(i => ({ ...i, isNew: false }));
  const seen = new Set(items.map(i => i.file));
  for (const [f, v] of Object.entries(S.icons)) {
    if (v.isNew && !seen.has(f)) {
      items.push({
        file: f, url: v.url, w: 168, h: 168,
        packages: v.pkg ? [v.pkg] : [], system: false, isNew: true,
      });
    }
  }

  const list = q ? items.filter(i =>
    i.file.toLowerCase().includes(q) ||
    i.packages.some(p => p.toLowerCase().includes(q)) ||
    appName(i.packages[0]).toLowerCase().includes(q)) : items;

  if (!list.length) {
    box.innerHTML = '<div class="hint" style="grid-column:1/-1">没有匹配的图标</div>';
    return;
  }

  box.innerHTML = list.map(i => {
    const ch = S.icons[i.file];
    const rm = S.iconRemoved.includes(i.file);
    const cls = rm ? 'removed' : (i.isNew ? 'brandnew' : (ch ? 'changed' : ''));
    const src = ch && !rm ? ch.url : i.url;
    const badge = rm ? '<b class="ib ib-rm">移除</b>'
      : i.isNew ? '<b class="ib ib-new">新</b>'
        : ch ? '<b class="ib ib-ch">改</b>' : '';
    const delTitle = rm ? '恢复' : (i.isNew ? '删除' : '从主题中移除');
    return `<div class="icon-cell ${cls}" data-file="${esc(i.file)}" title="${esc(i.file)}">
      <img src="${src}" alt="" loading="lazy">
      <div class="nm">${esc(appName(i.packages[0]))}</div>
      <span class="isz">${i.w || 168}×${i.h || 168}</span>
      ${badge}
      <button class="iop iop-del" data-del="${esc(i.file)}" title="${delTitle}">×</button>
      ${ch && !i.isNew && !rm ? `<button class="iop iop-undo" data-undo="${esc(i.file)}" title="撤销替换">↺</button>` : ''}
    </div>`;
  }).join('');
}

/* ---------------- 新增图标 ---------------- */
function openAddIcon() {
  const size = S.detail?.icons[0] ? `${S.detail.icons[0].w}×${S.detail.icons[0].h}` : '168×168';
  showModal(`
    <div style="padding:20px;width:430px;max-width:86vw">
      <h3 style="font-size:16px;margin-bottom:6px">新增图标</h3>
      <p class="hint" style="margin-bottom:14px">给模板里没有覆盖的应用补图标。文件名一般直接用包名，例如 com.example.app.png。</p>
      <div class="field"><label>图标文件名 *</label>
        <input class="input" id="newIconName" placeholder="com.example.app.png"></div>
      <div class="field"><label>应用包名（可选）</label>
        <input class="input" id="newIconPkg" placeholder="com.example.app">
        <div class="hint">填了包名，桌面才知道把这张图套给哪个应用</div></div>
      <div class="field"><label>图片（建议 ${size} 正方形）</label>
        <input class="input" type="file" id="newIconFile" accept="image/*" style="height:auto;padding:8px"></div>
      <div style="display:flex;gap:9px;margin-top:16px">
        <button class="btn" id="newIconCancel" style="flex:1">取消</button>
        <button class="btn primary" id="newIconOk" style="flex:1">添加</button>
      </div>
    </div>`);

  $('#newIconCancel').onclick = closeModal;
  $('#newIconOk').onclick = async () => {
    const raw = $('#newIconName').value.trim();
    const pkg = $('#newIconPkg').value.trim();
    const file = $('#newIconFile').files[0];
    if (!raw) return toast('先填个文件名');
    if (!file) return toast('选一张图片');
    const name = raw.toLowerCase().endsWith('.png') ? raw : raw + '.png';
    if (S.detail?.icons.some(i => i.file === name)) return toast('这个文件名已经存在，直接点它替换即可');
    try {
      const up = await uploadFile(file);
      S.icons[name] = { upload: up.id, url: up.url, isNew: true, pkg };
      S.iconRemoved = S.iconRemoved.filter(x => x !== name);
      closeModal();
      renderPanel();
      renderIconPreview();
      toast(`已新增 ${name}（${up.w}×${up.h}）`);
    } catch (e) {
      toast('失败：' + e.message, 3200);
    }
  };
}

function closeModal() {
  $('#modal').classList.remove('show');
}

/* 自定义改色弹窗：hex 输入 + 原生取色器 + 预设色块 + 确认/清除 */
function openColorModal({ title, init, onPick, onClear }) {
  const presetHex = PRESETS.map(p => toSimpleHex(p));
  showModal(`
    <div style="padding:20px;width:360px;max-width:88vw">
      <h3 style="font-size:16px;margin-bottom:4px">${title}</h3>
      <p class="hint" style="margin-bottom:14px">输入任意十六进制色值，或用取色器/预设色块。清除后回到自动配色。</p>
      <div class="color-row">
        <input type="color" id="cmPick" value="${init}">
        <input class="input" id="cmHex" value="${init}" maxlength="7" spellcheck="false" placeholder="#RRGGBB">
      </div>
      <div class="presets" id="cmPresets" style="margin-top:12px">
        ${presetHex.map(c => `<button class="preset" data-c="${c}" style="background:${c}"></button>`).join('')}
      </div>
      <div style="display:flex;gap:9px;margin-top:18px">
        <button class="btn" id="cmClear" style="flex:1">清除（还原自动）</button>
        <button class="btn primary" id="cmOk" style="flex:1">确定</button>
      </div>
    </div>`);

  const pick = $('#cmPick'), hex = $('#cmHex');
  const sync = (c, fromPicker) => {
    const n = normHex(c);
    if (n.length !== 7) return;
    hex.value = toSimpleHex(n);
    if (!fromPicker) pick.value = toSimpleHex(n);
  };
  pick.oninput = () => sync(pick.value, true);
  hex.oninput = () => sync(hex.value, false);
  $$('#cmPresets .preset').forEach(b => b.onclick = () => {
    pick.value = b.dataset.c; hex.value = b.dataset.c;
  });
  $('#cmOk').onclick = () => {
    const n = normHex(hex.value);
    if (n.length !== 7) return toast('颜色格式不对，要 #RRGGBB');
    closeModal();
    onPick && onPick('#' + n.slice(1));
  };
  $('#cmClear').onclick = () => {
    closeModal();
    onClear && onClear();
  };
}

/* ---------------- 商店预览图 ---------------- */
function previewDelete(key) {
  const item = (S.detail?.previews || []).find(p => p.key === key);
  const ov = S.previews[key];

  // 自己加的图:直接删记录
  if (ov && !ov.path) {
    delete S.previews[key];
    renderPanel();
    toast('已移除 ' + key);
    return;
  }
  // 模板原有的图:标记为打包时删除
  if (item && !S.previewRemoved.includes(item.path)) {
    S.previewRemoved.push(item.path);
  }
  delete S.previews[key];
  renderPanel();
  toast('打包时会去掉这张：' + key, 3000);
}

/* ---------------- 图标：删除 / 批量导入 ---------------- */
function iconToggleDelete(file) {
  const v = S.icons[file];
  if (v && v.isNew) {
    delete S.icons[file];
    toast('已删除 ' + file);
  } else {
    const idx = S.iconRemoved.indexOf(file);
    if (idx >= 0) {
      S.iconRemoved.splice(idx, 1);
      toast('已恢复到主题');
    } else {
      S.iconRemoved.push(file);
      delete S.icons[file];
      toast('打包时将移除 ' + file);
    }
  }
  renderPanel();
  renderIconPreview();
}

const PKG_RE = /^[A-Za-z][\w-]*(\.[\w-]+)+$/;

async function importIcons(files) {
  const pngs = files.filter(f => /\.png$/i.test(f.name));
  if (!pngs.length) { toast('请选择 PNG 文件'); return; }

  const known = new Set(S.detail.icons.map(i => i.file));
  let rep = 0, add = 0, noPkg = 0, fail = 0;
  const BATCH = 20;

  for (let i = 0; i < pngs.length; i += BATCH) {
    const chunk = pngs.slice(i, i + BATCH);
    toast(`正在导入 ${Math.min(i + BATCH, pngs.length)} / ${pngs.length} …`, 8000);
    const items = [];
    for (const f of chunk) {
      try { items.push({ name: f.name, data: await fileToDataURL(f) }); }
      catch { fail++; }
    }
    let r;
    try { r = await api('/api/upload_batch', { items }); }
    catch (e) { toast('上传失败：' + e.message, 4000); fail += items.length; continue; }

    for (const up of r.items) {
      if (up.error) { fail++; continue; }
      const name = up.name;
      if (!/\.png$/i.test(name)) continue;
      const base = name.replace(/\.png$/i, '');
      const isPkg = PKG_RE.test(base);
      if (known.has(name)) {
        S.icons[name] = { upload: up.id, url: up.url };
        rep++;
      } else {
        S.icons[name] = { upload: up.id, url: up.url, isNew: true, pkg: isPkg ? base : '' };
        add++;
        if (!isPkg) noPkg++;
      }
      S.iconRemoved = S.iconRemoved.filter(x => x !== name);
      known.add(name);
    }
    await new Promise(r2 => setTimeout(r2, 0));
  }

  renderPanel();
  renderIconPreview();
  let msg = `替换 ${rep} · 新增 ${add}`;
  if (noPkg) msg += ` · ${noPkg} 个文件名不像包名，仅作图片加入`;
  if (fail) msg += ` · 失败 ${fail}`;
  toast('导入完成：' + msg, 5000);
}

/* ---------------- 上传 ---------------- */
let pickCtx = null;
function pickFile(kind, multiple, arg) {
  pickCtx = { kind, arg };
  const inp = $('#filePick');
  inp.value = '';
  inp.multiple = !multiple;
  if (kind === 'theme') { inp.accept = '.theme'; }
  else inp.accept = 'image/*';
  inp.onchange = async () => {
    const files = [...inp.files];
    if (!files.length) return;
    await handleFiles(files, pickCtx);
  };
  inp.click();
}

async function handleFiles(files, ctx) {
  try {
    if (ctx.kind === 'theme') {
      const f = files[0];
      toast('正在导入 ' + f.name + ' …', 4000);
      const data = await fileToDataURL(f);
      const r = await api('/api/template/upload', { data, name: f.name.replace(/\.theme$/i, '') });
      await loadTemplates();
      toast('导入成功：' + (r.summary || r.file));
      selectTemplate(r.id);
      return;
    }
    if (ctx.kind === 'wallpaper') {
      await applyWallpaper(files[0], ctx.arg);
      return;
    }
    if (ctx.kind === 'icon') {
      const f = files[0];
      const up = await uploadFile(f);
      S.icons[ctx.arg] = { upload: up.id, url: up.url };
      S.iconRemoved = S.iconRemoved.filter(x => x !== ctx.arg);
      renderIconGrid(); renderIconPreview();
      toast('已替换 ' + ctx.arg);
      return;
    }
    if (ctx.kind === 'asset') {
      const f = files[0];
      const up = await uploadFile(f);
      S.assets[ctx.arg] = { upload: up.id, url: up.url };
      // 改完直接跳到能看到它的界面
      const view = ASSET_VIEW[ctx.arg];
      if (view) S.view = view;
      if (S.step === 'assets') renderPanel();
      updatePreview();
      toast(`已替换 ${ctx.arg}（${up.w}×${up.h}）${view ? ' · 已切到预览' : ''}`, 3500);
      return;
    }
    if (ctx.kind === 'preview') {
      const up = await uploadFile(files[0]);
      const key = ctx.arg;
      const item = (S.detail?.previews || []).find(p => p.key === key);
      S.previews[key] = {
        upload: up.id, url: up.url, w: up.w, h: up.h,
        path: item?.path || '',
        name: item ? '' : `preview_${key}.png`,
      };
      if (item) S.previewRemoved = S.previewRemoved.filter(x => x !== item.path);
      if (S.step === 'assets') renderPanel();
      toast(item ? `预览图已替换（${up.w}×${up.h}）` : '预览图已添加', 2800);
      return;
    }
    if (ctx.kind === 'icons') {
      await importIcons(files);
    }
  } catch (e) {
    toast('失败：' + e.message, 3200);
  }
}

async function applyWallpaper(file, role) {
  try {
    toast('正在处理壁纸…', 3000);
    const up = await uploadFile(file, { dominant: true });
    if (role === 'home') { S.wallpaper = up.id; S.wallpaperUrl = up.url; }
    else { S.lockscreen = up.id; S.lockscreenUrl = up.url; }
    updatePreview();
    if (S.step === 'wallpaper') renderPanel();
    if (up.dominant) S.lastWallDominant = up.dominant;
    toast('壁纸已应用' + (up.w > 0 ? `（${up.w}×${up.h}）` : ''));
  } catch (e) {
    toast('失败：' + e.message, 3200);
  }
}

function pickFromWall() {
  const c = S.lastWallDominant;
  if (c) { setPrimary(c); toast('已取色 ' + toSimpleHex(c)); return; }
  const src = S.wallpaperUrl;
  if (!src) { toast('先上传一张壁纸再取色'); return; }
  // 前端兜底:从图片上采样
  const img = new Image();
  img.crossOrigin = 'anonymous';
  img.onload = () => {
    const cv = document.createElement('canvas');
    cv.width = 64; cv.height = 64;
    const ctx = cv.getContext('2d');
    ctx.drawImage(img, 0, 0, 64, 64);
    const d = ctx.getImageData(0, 0, 64, 64).data;
    const buckets = {};
    for (let i = 0; i < d.length; i += 4) {
      const [h, s, l] = rgbToHsl(d[i], d[i + 1], d[i + 2]);
      if (s < 18 || l < 15 || l > 90) continue;
      const k = Math.round(h / 15);
      buckets[k] = (buckets[k] || 0) + 1;
    }
    let best = 0, bi = 0;
    for (const k in buckets) if (buckets[k] > best) { best = buckets[k]; bi = +k; }
    setPrimary(hslToHex(bi * 15, 72, 58));
    toast('已取色');
  };
  img.src = src;
}

/* ---------------- 导出 ---------------- */
async function doBuild() {
  if (!S.tpl) { toast('先选择模板'); return; }
  if (!S.name.trim()) { toast('主题名不能为空'); return; }
  S.busy = true;
  renderPanel();
  try {
    const previews = {}, previewAdd = [];
    for (const [k, v] of Object.entries(S.previews)) {
      if (v.path && !S.previewRemoved.includes(v.path)) previews[k] = v.upload;
      else previewAdd.push({ name: v.name || `preview_${k}.png`, upload: v.upload });
    }
    const body = {
      tpl: S.tpl,
      name: S.name, author: S.author, description: S.description,
      version_name: S.versionName, version_code: S.versionCode, uuid: S.uuid,
      primary: S.primary, anchor: S.anchor, strength: S.strength,
      hue_only: S.hueOnly, protect_neutrals: S.protect, tint_light: S.tintLight,
      recolor: S.recolor,
      overrides: S.overrides,
      wallpaper: S.wallpaper, lockscreen: S.lockscreen,
      wallpaper_fit: S.wallpaperFit,
      assets: Object.entries(S.assets).map(([file, v]) => ({ file, upload: v.upload, sync: true })),
      asset_fit: S.assetFit,
      asset_compress: S.assetCompress,
      previews, preview_add: previewAdd, preview_remove: S.previewRemoved.slice(),
      is_global: S.isGlobal,
      icons: Object.entries(S.icons).map(([name, v]) => ({ name, upload: v.upload })),
      icon_packages: Object.fromEntries(
        Object.entries(S.icons).filter(([, v]) => v.pkg).map(([n, v]) => [n, v.pkg])),
      icon_remove: S.iconRemoved.slice(),
      icon_shape: S.iconShape, icon_scale: S.iconScale,
      tint_systemui: S.tint,
    };
    const r = await api('/api/build', body);
    S.lastResult = r;
    S.busy = false;
    renderPanel();
    toast('生成成功 · ' + (r.size / 1048576).toFixed(2) + ' MB', 3200);
  } catch (e) {
    S.busy = false;
    S.lastResult = { error: e.message };
    renderPanel();
    toast('生成失败：' + e.message, 4000);
  }
}

async function loadOutputs() {
  try {
    const r = await api('/api/outputs');
    const box = $('#outputList');
    if (!box) return;
    box.innerHTML = r.outputs.length ? r.outputs.map(o => `
      <div class="out-item">
        <div><div>${esc(o.file)}</div><small>${o.time} · ${(o.size / 1048576).toFixed(2)} MB</small></div>
        <a href="${o.download}">下载</a>
      </div>`).join('') : '<div class="hint">还没有生成过主题</div>';
  } catch { /* ignore */ }
}

function randomUuid() {
  const h = '0123456789ABCDEF';
  let s = '';
  for (let i = 0; i < 32; i++) s += h[Math.floor(Math.random() * 16)];
  return s;
}

function showModal(html) {
  $('#modalBox').innerHTML = html;
  $('#modal').classList.add('show');
}

/* ---------------- 初始化 ---------------- */
function init() {
  const hash = (location.hash || '').replace('#', '');
  const VIEWS = ['home', 'lock', 'cc', 'volume', 'notify', 'settings', 'sms', 'dialer', 'about'];
  if (VIEWS.includes(hash)) S.view = hash;
  if (['template', 'color', 'wallpaper', 'icons', 'assets', 'meta'].includes(hash)) {
    S.step = hash;
    S.hashStep = hash;
  }
  const q = new URLSearchParams(location.search);
  S.urlPrimary = q.get('primary') || null;
  S.urlName = q.get('name') || null;
  S.urlTpl = q.get('tpl') || null;
  $$('.step').forEach(b => b.onclick = () => {
    S.step = b.dataset.step;
    renderPanel();
  });
  $$('#viewSeg button').forEach(b => b.onclick = () => {
    S.view = b.dataset.view;
    updatePreview();
  });
  $('#modal').onclick = e => { if (e.target.id === 'modal') $('#modal').classList.remove('show'); };
  $('#btnExportTop').onclick = () => {
    if (!S.tpl) { toast('先选择模板'); return; }
    S.step = 'meta'; renderPanel();
  };
  $('#btnReloadTpl').onclick = async () => {
    if (!S.tpl) { toast('还没选模板'); return; }
    await selectTemplate(S.tpl);
    toast('已重新解析');
  };

  // 全局拖入 .theme
  document.addEventListener('dragover', e => e.preventDefault());
  document.addEventListener('drop', async e => {
    const f = e.dataTransfer?.files?.[0];
    if (!f) return;
    if (f.name.toLowerCase().endsWith('.theme')) {
      e.preventDefault();
      await handleFiles([f], { kind: 'theme' });
    }
  });

  setAccent(S.primary);
  loadTemplates().then(() => {
    // 自动载入上次用过的模板，没有就载入第一个
    let last = null;
    try { last = localStorage.getItem(TPL_KEY); } catch { /* 隐私模式 */ }
    const pick = S.templates.find(t => t.id === (S.urlTpl || last)) || S.templates[0];
    if (pick) selectTemplate(pick.id);
    else renderPanel();
  }).catch(e => toast('服务未就绪：' + e.message, 4000));
  updatePreview();

}

document.addEventListener('DOMContentLoaded', init);
})();
