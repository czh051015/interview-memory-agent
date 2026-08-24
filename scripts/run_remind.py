"""面试前提醒 —— 按遗忘状态分层，动态提醒你栽过的题。

用法：
  python run_remind.py                  # 全部公司，打印完整分层
  python run_remind.py 字节              # 只提醒字节相关的题
  python run_remind.py 字节 AI应用开发    # 公司 + 岗位
  python run_remind.py --notify         # 静默检查：有「快忘了」的题才弹桌面通知，否则静默退出

逻辑：检索 fail/partial → 按公司过滤 → rank 双因子排序 → 按掌握度缺口分层
  🔴 快忘了（gap ≥ 0.5）  —— 优先看
  🟡 该看看（0.2 ≤ gap < 0.5）
  ✅ 最近刚看过（gap < 0.2）—— 只提示数量，不展开

「动态」体现在：分层不是写死的清单，是实时按你的遗忘状态算出来的。
--notify 模式供定时任务（每天 22:00）调用：没有快忘的题就闭嘴，不打扰你。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sys
import io
import base64
import subprocess
import logging
from datetime import datetime
from xml.sax.saxutils import escape as _xml_escape

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

from src.memory import knowledge_store as store
from src.memory.mastery import layer, _elapsed_days
from src.cleaner.schema import utcnow
import src.config as _cfg  # noqa: E402  （SPACE：--space / OFFERLOOP_SPACE 切换）


def _load_review_items() -> list:
    """所有 fail + partial 的题（pass/unknown 过滤），限当前空间。"""
    return (
        store.search(status="fail", space=_cfg.SPACE, top_k=1000)
        + store.search(status="partial", space=_cfg.SPACE, top_k=1000)
    )


# Windows toast 的 AppId 必须匹配开始菜单里真实存在的快捷方式，否则 CreateToastNotifier 抛异常。
# PowerShell 5.1 的 AUMID 一定存在，免注册、免管理员权限（自 1709 起瞎编的 AppId 会失败）。
_TOAST_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def _notify_windows(title: str, body: str) -> bool:
    """Windows 桌面 toast 通知（零第三方依赖，走 PowerShell）。

    用 base64 传 XML，避免转义地狱；AppId 用 PowerShell 自身的 AUMID。
    返回是否成功（returncode==0）。
    """
    xml = (
        '<toast><visual><binding template="ToastText02">'
        f'<text id="1">{_xml_escape(title)}</text>'
        f'<text id="2">{_xml_escape(body)}</text>'
        "</binding></visual></toast>"
    )
    b64 = base64.b64encode(xml.encode("utf-8")).decode("ascii")
    ps = (
        f"$b64 = '{b64}'\n"
        "$xmlStr = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($b64))\n"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null\n"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null\n"
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
        "$xml.LoadXml($xmlStr)\n"
        "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml\n"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{_TOAST_APP_ID}').Show($toast)\n"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            capture_output=True,
            timeout=30,
        )
        if r.returncode != 0:
            err = (r.stderr or b"").decode("utf-8", errors="ignore").strip()
            print(f"[toast 失败] PowerShell 退出码 {r.returncode}: {err[:400]}")
        return r.returncode == 0
    except Exception as e:
        print(f"[toast 异常] {e}")
        return False


def _notify_mode() -> int:
    """静默检查：只有「快忘了」(gap≥0.5) 的题才弹通知，否则静默退出。

    供每天定时任务调用——不打扰，只在真有遗忘时提醒。
    v2：走记忆管家 Agent（LLM 生成复习建议 + 薄弱主题），LLM 失败自动回退规则版。
    """
    from src.memory import memory_keeper as keeper

    try:
        return _notify_mode_keeper(keeper)
    except Exception as e:
        logging.error("记忆管家模式异常，回退规则版：%s", e)
        return _notify_mode_rule()


def _notify_mode_keeper(keeper) -> int:
    """记忆管家版：读快照 → LLM 规划 → 有快忘的才弹。"""
    plan = keeper.run(_cfg.SPACE, notify=True)
    red_count = len(keeper.read_memory_state(_cfg.SPACE).red)
    if red_count == 0:
        return 0  # 没有快忘的题，静默
    if plan.get("plan"):
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] 记忆管家已提醒 {len(plan['plan'])} 道题")
    return 0


def _notify_mode_rule() -> int:
    """规则版（原实现）：gap≥0.5 的题弹通知，不依赖 LLM。"""
    now = utcnow()
    items = _load_review_items()
    if not items:
        return 0

    red, _, _ = layer(items, now=now)
    if not red:
        return 0  # 没有快忘的题，静默

    title = f"OfferLoop 提醒：{len(red)} 道题快忘了"
    lines = []
    for it in red[:3]:
        days = int(_elapsed_days(it, now))
        lines.append(f"[{it.status.value.upper()}] {it.question}（{days}天没复习）")
    body = "\n".join(lines)
    if len(red) > 3:
        body += f"\n……还有 {len(red) - 3} 道"
    body += "\n\n跑 python run_review.py 复习"

    if _notify_windows(title, body):
        print(f"[{now:%Y-%m-%d %H:%M}] 已弹窗提醒 {len(red)} 道快忘的题")
        return 0
    # 桌面弹窗不可用（权限/专注助手等），退回控制台打印，定时任务日志里仍能看到提醒
    print(f"[{now:%Y-%m-%d %H:%M}] {title}")
    print(body)
    return 0


def main() -> int:
    args = sys.argv[1:]

    if "--notify" in args:
        return _notify_mode()

    company = args[0] if args else None
    role = args[1] if len(args) > 1 else None

    now = utcnow()
    items = _load_review_items()

    if company:
        items = [it for it in items if it.company and company in it.company]
    if role:
        items = [it for it in items if it.role and role in it.role]

    if not items:
        print(f"没有找到 {company or '全部公司'}{' · ' + role if role else ''} 相关、你栽过的题。")
        print("先跑 run_interview.py 录复盘 / annotate_jingyan.py 标注错题。")
        return 0

    red, yellow, green = layer(items, now=now)

    label = f"{company or '全部公司'}" + (f" · {role}" if role else "")
    print(f"\n📋 面试前提醒（{label}）")
    print(f"   你之前在这 {len(items)} 道题上栽过，按遗忘程度分层：\n")

    if red:
        print(f"🔴 快忘了（{len(red)} 道，优先看）：")
        for it in red:
            days = int(_elapsed_days(it, now))
            print(f"   [{it.status.value.upper():>7}] {it.question}  ({it.topic})  {days} 天没复习")
            if it.behavior_tags:
                print(f"      ⚠️ 行为提醒：{', '.join(it.behavior_tags)}")
        print()

    if yellow:
        print(f"🟡 该看看（{len(yellow)} 道）：")
        for it in yellow:
            days = int(_elapsed_days(it, now))
            print(f"   [{it.status.value.upper():>7}] {it.question}  ({it.topic})  {days} 天没复习")
            if it.behavior_tags:
                print(f"      ⚠️ 行为提醒：{', '.join(it.behavior_tags)}")
        print()

    if green:
        print(f"✅ 最近刚看过 {len(green)} 道，掌握度还高，暂不提醒。")

    print("\n💡 看完这些，跑 python run_review.py 复习，或准备模拟面试。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
