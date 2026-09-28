"""无头浏览器工厂: 反检测 + 登录会话持久化 + SOCKS 代理。

DrissionPage 4.1.x 的 auto_port() 会无条件用临时目录覆盖
set_user_data_path(库 bug, 见其 handle_options 源码), 登录态无法持久,
必须用 set_local_port() 固定端口。--headless=new + 关闭
AutomationControlled + 真实 UA 可过抖音反无头检测。
"""
import os
from typing import Optional

from DrissionPage import ChromiumOptions, ChromiumPage

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_PROFILE = os.path.join(_BASE, "browser_data_hd")
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def new_page(port: int = 9337,
             profile: Optional[str] = None,
             proxy: str = "socks5://127.0.0.1:1080",
             headless: bool = True) -> ChromiumPage:
    """启动 Chrome(独立配置目录, 登录态跨次保留)。

    Args:
        port: 本地调试端口。不要用 auto_port, 见模块 docstring。
        profile: 用户配置目录路径, 默认项目下 browser_data_hd。
        proxy: SOCKS 代理地址, 空串表示不走代理。
        headless: True=无窗口后台运行; False=可见窗口
            (扫码登录等需要人工操作的场景)。

    Returns:
        已启动的 ChromiumPage 实例。
    """
    co = ChromiumOptions()
    if headless:
        co.set_argument("--headless=new")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_user_agent(_UA)
    if proxy:
        co.set_argument("--proxy-server=" + proxy)
    co.set_local_port(port)
    co.set_user_data_path(profile or _DEFAULT_PROFILE)
    return ChromiumPage(addr_or_opts=co)
