[app]

# 应用名称（显示在手机桌面图标下）
title = 城市天气记录器

# 包名（小写，无空格无中文）
package.name = weatherlogger

# 包域名（反写域名，随便填一个唯一的）
package.domain = org.example

# 源码目录（当前目录）
source.dir = .

# 打包进 APK 的文件类型
source.include_exts = py,png,jpg,kv,atlas,ttf,ttc

# 应用版本
version = 1.0

# 依赖：python3 + kivy + 网络证书相关
# 程序只用到标准库 urllib，无第三方运行时依赖
requirements = python3,kivy,certifi,openssl

# 屏幕方向：竖屏
orientation = portrait

# 全屏（0=保留状态栏，1=全屏）
fullscreen = 0

# 入口文件（默认 main.py，无需改名）
# Buildozer 默认就是 main.py

# ===== 安卓权限 =====
# INTERNET：联网抓取数据
# ACCESS_NETWORK_STATE：检测网络状态
android.permissions = INTERNET,ACCESS_NETWORK_STATE

# 目标 / 最低 安卓 API
android.api = 33
android.minapi = 24

# 支持的 CPU 架构（只用 arm64-v8a，绝大多数现代手机都是 64 位）
android.archs = arm64-v8a

# 锁定 NDK 版本（25b 是 python-for-android 最稳定支持的版本）
android.ndk = 25b

# 自动接受 SDK 许可协议（首次打包必需，否则会卡在询问）
android.accept_sdk_license = True

# 备份开关
android.allow_backup = True

[buildozer]

# 日志级别：2 = 详细，方便排错
log_level = 2

# 出现 root 警告时是否继续
warn_on_root = 1
