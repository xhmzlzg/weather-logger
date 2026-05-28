# -*- coding: utf-8 -*-
"""
中央气象台实时气象数据记录器（Kivy 安卓版）
- 选择省份和城市后立即抓取一次，并每 10 分钟记录一次
- 抓取：实时气温、降水量、风向风速、相对湿度、体感温度、空气质量
- 数据来源：中国中央气象台 https://www.nmc.cn
"""

import csv
import json
import os
import ssl
import threading
import urllib.request
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView


BASE = "https://www.nmc.cn"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": BASE}
INTERVAL_SEC = 10 * 60
CSV_NAME = "weather_records.csv"

# 安卓上打包的 Python 没有内置根证书，跳过 SSL 验证（天气数据无敏感性）
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

CSV_COLUMNS = [
    "记录时间", "省份", "城市", "数据发布时间", "天气",
    "气温(℃)", "降水量(mm)", "风向", "风速(m/s)", "风力",
    "相对湿度(%)", "体感温度(℃)", "空气质量指数(AQI)", "空气质量",
]


def get_storage_dir():
    """安卓上写入 App 私有外部存储；桌面上写当前目录。"""
    try:
        from android.storage import app_storage_path  # type: ignore
        path = app_storage_path()
        os.makedirs(path, exist_ok=True)
        return path
    except Exception:
        return os.getcwd()


def register_cjk_font():
    """安卓系统自带 DroidSansFallback 支持中文；桌面尝试常见中文字体。"""
    candidates = [
        "/system/fonts/NotoSansCJK-Regular.ttc",
        "/system/fonts/DroidSansFallback.ttf",
        "/system/fonts/DroidSansFallbackFull.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                LabelBase.register(name="CJK", fn_regular=path)
                return "CJK"
            except Exception:
                continue
    return "Roboto"


# ========== 网络与解析（纯逻辑，可直接复用） ==========

def http_get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_provinces():
    return http_get_json(f"{BASE}/rest/province/all")


def fetch_cities(province_code):
    return http_get_json(f"{BASE}/rest/province/{province_code}")


def fetch_weather(station_code):
    return http_get_json(f"{BASE}/rest/weather?stationid={station_code}")


def parse_weather(data, province, city):
    real = data.get("data", {}).get("real", {})
    air = data.get("data", {}).get("air", {})
    weather = real.get("weather", {})
    wind = real.get("wind", {})

    def clean(v):
        if v in (9999, 9999.0, "9999", -1, "-1", None, ""):
            return "—"
        return v

    return {
        "记录时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "省份": province,
        "城市": city,
        "数据发布时间": clean(real.get("publish_time")),
        "天气": clean(weather.get("info")),
        "气温(℃)": clean(weather.get("temperature")),
        "降水量(mm)": clean(weather.get("rain")),
        "风向": clean(wind.get("direct")),
        "风速(m/s)": clean(wind.get("speed")),
        "风力": clean(wind.get("power")),
        "相对湿度(%)": clean(weather.get("humidity")),
        "体感温度(℃)": clean(weather.get("feelst")),
        "空气质量指数(AQI)": clean(air.get("aqi")),
        "空气质量": clean(air.get("text")),
    }


# ========== UI 组件 ==========

class PickerButton(Button):
    """点击后弹出可滚动列表的选择按钮，适合大量项目（省/市）。"""
    placeholder = StringProperty("请选择")

    def __init__(self, font_name="Roboto", on_pick=None, **kwargs):
        super().__init__(**kwargs)
        self.font_name = font_name
        self.font_size = dp(18)
        self.size_hint_y = None
        self.height = dp(54)
        self.text = self.placeholder
        self.on_pick = on_pick
        self._items = []  # [(label, value)]
        self.bind(on_release=self._open)

    def set_items(self, items):
        self._items = items
        self.text = self.placeholder

    def _open(self, *_):
        if not self._items:
            return
        content = BoxLayout(orientation="vertical", spacing=dp(2), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))
        popup = Popup(
            title=self.placeholder,
            title_font=self.font_name,
            size_hint=(0.9, 0.85),
        )
        for label, value in self._items:
            btn = Button(
                text=label,
                font_name=self.font_name,
                font_size=dp(18),
                size_hint_y=None,
                height=dp(52),
            )

            def _choose(_btn, lbl=label, val=value):
                self.text = lbl
                if self.on_pick:
                    self.on_pick(lbl, val)
                popup.dismiss()

            btn.bind(on_release=_choose)
            content.add_widget(btn)

        scroll = ScrollView()
        scroll.add_widget(content)
        popup.content = scroll
        popup.open()


class RecordRow(BoxLayout):
    """记录列表中的一行（关键字段，点击查看完整信息）。"""

    def __init__(self, row, font_name="Roboto", **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         height=dp(56), padding=(dp(8), dp(4)),
                         spacing=dp(6), **kwargs)
        self.row = row
        self.font_name = font_name

        time_part = row["记录时间"].split(" ")[-1][:5]  # HH:MM
        text = (
            f"[b]{time_part}[/b]  {row['城市']}\n"
            f"{row['天气']}  {row['气温(℃)']}℃  "
            f"湿度{row['相对湿度(%)']}%  AQI {row['空气质量指数(AQI)']}"
        )
        self.label = Label(
            text=text, markup=True, font_name=font_name,
            font_size=dp(15), halign="left", valign="middle",
        )
        self.label.bind(size=lambda *_: setattr(self.label, "text_size", self.label.size))
        self.add_widget(self.label)

        detail_btn = Button(text="详情", font_name=font_name,
                            size_hint_x=None, width=dp(72))
        detail_btn.bind(on_release=self._show_detail)
        self.add_widget(detail_btn)

    def _show_detail(self, *_):
        lines = [f"{k}：{self.row[k]}" for k in CSV_COLUMNS]
        content_label = Label(
            text="\n".join(lines), font_name=self.font_name,
            font_size=dp(16), halign="left", valign="top",
            size_hint_y=None,
        )
        content_label.bind(
            size=lambda *_: setattr(content_label, "text_size", content_label.size),
            texture_size=lambda *_: setattr(content_label, "height", content_label.texture_size[1]),
        )
        scroll = ScrollView()
        scroll.add_widget(content_label)
        Popup(title="记录详情", title_font=self.font_name,
              size_hint=(0.9, 0.8), content=scroll).open()


# ========== 主界面 ==========

class WeatherRoot(BoxLayout):
    def __init__(self, font_name, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10),
                         spacing=dp(8), **kwargs)
        self.font_name = font_name
        self.provinces = []          # 原始数据
        self.province_code = None
        self.city_code = None
        self.province_name = ""
        self.city_name = ""
        self.running = False
        self.tick_event = None
        self.record_count = 0
        self.csv_path = os.path.join(get_storage_dir(), CSV_NAME)

        # 标题
        title = Label(
            text="中央气象台实时气象数据记录器", font_name=font_name,
            font_size=dp(20), bold=True, size_hint_y=None, height=dp(40),
        )
        self.add_widget(title)

        # 省份/城市选择
        self.province_btn = PickerButton(
            font_name=font_name, on_pick=self._on_pick_province,
        )
        self.province_btn.placeholder = "选择省份"
        self.province_btn.text = "选择省份"
        self.add_widget(self.province_btn)

        self.city_btn = PickerButton(
            font_name=font_name, on_pick=self._on_pick_city,
        )
        self.city_btn.placeholder = "选择城市"
        self.city_btn.text = "选择城市"
        self.add_widget(self.city_btn)

        # 开始/停止按钮
        btn_bar = BoxLayout(orientation="horizontal", spacing=dp(8),
                            size_hint_y=None, height=dp(54))
        self.start_btn = Button(text="开始记录", font_name=font_name,
                                font_size=dp(18))
        self.start_btn.bind(on_release=self._toggle)
        self.fetch_now_btn = Button(text="立即抓取一次", font_name=font_name,
                                    font_size=dp(18))
        self.fetch_now_btn.bind(on_release=lambda *_: self._tick(force=True))
        btn_bar.add_widget(self.start_btn)
        btn_bar.add_widget(self.fetch_now_btn)
        self.add_widget(btn_bar)

        # 状态条
        self.status_label = Label(
            text=f"CSV 文件：{self.csv_path}", font_name=font_name,
            font_size=dp(13), size_hint_y=None, height=dp(70),
            halign="left", valign="top",
        )
        self.status_label.bind(
            size=lambda *_: setattr(self.status_label, "text_size",
                                    (self.status_label.width, None))
        )
        self.add_widget(self.status_label)

        self.count_label = Label(
            text="已记录 0 条", font_name=font_name, font_size=dp(14),
            size_hint_y=None, height=dp(28),
        )
        self.add_widget(self.count_label)

        # 记录列表
        list_title = Label(text="── 历史记录 ──", font_name=font_name,
                           font_size=dp(14), size_hint_y=None, height=dp(28))
        self.add_widget(list_title)

        self.list_layout = BoxLayout(orientation="vertical",
                                     size_hint_y=None, spacing=dp(2))
        self.list_layout.bind(minimum_height=self.list_layout.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.list_layout)
        self.add_widget(scroll)

        # 启动后异步加载省份列表
        Clock.schedule_once(lambda *_: self._load_provinces(), 0.2)

    # ---------- 数据加载 ----------

    def _load_provinces(self):
        self._set_status("正在加载省份列表…")

        def work():
            try:
                data = fetch_provinces()
                items = [(p.get("name", ""), p.get("code", "")) for p in data]
                self._apply_provinces(items)
            except Exception as e:
                self._set_status(f"省份加载失败：{e}")

        threading.Thread(target=work, daemon=True).start()

    @mainthread
    def _apply_provinces(self, items):
        self.province_btn.set_items(items)
        self.province_btn.text = "选择省份"
        self._set_status("请选择省份")

    def _on_pick_province(self, label, value):
        self.province_name = label
        self.province_code = value
        self.city_btn.set_items([])
        self.city_btn.text = "正在加载城市…"
        self.city_code = None

        def work():
            try:
                data = fetch_cities(value)
                items = [(c.get("city", ""), c.get("code", "")) for c in data]
                self._apply_cities(items)
            except Exception as e:
                self._set_status(f"城市加载失败：{e}")

        threading.Thread(target=work, daemon=True).start()

    @mainthread
    def _apply_cities(self, items):
        self.city_btn.set_items(items)
        self.city_btn.text = "选择城市"
        self._set_status(f"已选省份：{self.province_name}，请选择城市")

    def _on_pick_city(self, label, value):
        self.city_name = label
        self.city_code = value
        self._set_status(f"已选：{self.province_name} / {self.city_name}")

    # ---------- 记录控制 ----------

    def _toggle(self, *_):
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self):
        if not self.city_code:
            self._set_status("请先选择省份和城市")
            return
        self.running = True
        self.start_btn.text = "停止记录"
        self._tick(force=True)

    def _stop(self):
        self.running = False
        self.start_btn.text = "开始记录"
        if self.tick_event is not None:
            self.tick_event.cancel()
            self.tick_event = None
        self._set_status("已停止记录")

    def _tick(self, force=False, *_):
        if not self.city_code:
            return

        def work():
            try:
                raw = fetch_weather(self.city_code)
                row = parse_weather(raw, self.province_name, self.city_name)
                self._on_record(row)
            except Exception as e:
                self._set_status(f"抓取失败：{e}（10 分钟后重试）")

        threading.Thread(target=work, daemon=True).start()

        # 仅在持续运行模式下排定下一次
        if self.running:
            if self.tick_event is not None:
                self.tick_event.cancel()
            self.tick_event = Clock.schedule_once(
                lambda *_: self._tick(), INTERVAL_SEC
            )

    @mainthread
    def _on_record(self, row):
        self.list_layout.add_widget(
            RecordRow(row, font_name=self.font_name), index=len(self.list_layout.children)
        )
        # 限制内存中最多保留 200 条，避免长期运行占用过多
        if len(self.list_layout.children) > 200:
            self.list_layout.remove_widget(self.list_layout.children[-1])

        try:
            self._save_csv(row)
        except Exception as e:
            self._set_status(f"写入 CSV 失败：{e}")
            return

        self.record_count += 1
        self.count_label.text = f"已记录 {self.record_count} 条（CSV：{self.csv_path}）"
        self._set_status(
            f"{row['记录时间']} 记录成功：{row['城市']} {row['气温(℃)']}℃，"
            f"下次抓取约 10 分钟后"
        )

    def _save_csv(self, row):
        new_file = not os.path.exists(self.csv_path)
        with open(self.csv_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)

    @mainthread
    def _set_status(self, text):
        self.status_label.text = text


class WeatherApp(App):
    title = "城市天气记录器"

    def build(self):
        font_name = register_cjk_font()
        # 桌面下给个合适窗口大小，模拟手机比例
        try:
            if not any(p in os.sys.platform for p in ("android",)):
                Window.size = (dp(380), dp(720))
        except Exception:
            pass
        return WeatherRoot(font_name=font_name)


if __name__ == "__main__":
    WeatherApp().run()
