"""run_remind toast 通知测试（mock PowerShell，不实际弹窗）。"""

import run_remind as rr


class TestToastNotify:
    def test_app_id_is_real_powershell_aumid(self):
        """AppId 必须是开始菜单里真实存在的 AUMID，不能是瞎编的字符串。"""
        assert "WindowsPowerShell" in rr._TOAST_APP_ID
        assert rr._TOAST_APP_ID.startswith("{1AC14E77")

    def test_notify_uses_real_appid(self, monkeypatch):
        """_notify_windows 生成的 PowerShell 脚本用真实 AppId，而非旧的 'OfferLoop'。"""
        captured = {}

        class FakeResult:
            returncode = 0

        def fake_run(args, **kwargs):
            captured["ps"] = args[-1]
            return FakeResult()

        monkeypatch.setattr(rr.subprocess, "run", fake_run)
        ok = rr._notify_windows("标题", "内容")
        assert ok is True
        assert rr._TOAST_APP_ID in captured["ps"]
        assert "CreateToastNotifier('OfferLoop')" not in captured["ps"]
