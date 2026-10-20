"""桌面和 mobile 的技能变化刷新、轮次归属及版本预览；API 全部使用测试回执。"""

import copy
import os
import unittest
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


class SkillChangesBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.url = os.environ.get("SEARCHOS_TEST_URL", "http://127.0.0.1:3000")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.counts = {"old": 0, "new": 0}
        self.finished = False
        self.item = {"session_id": "skill-fixture", "title": "技能变化测试会话", "status": "completed", "coverage_score": None, "updated_at": 1, "project": "", "tags": [], "favorite": False, "archived": False}
        self.detail = {**self.item, "query": self.item["title"], "answer": "第二轮报告已完成。", "search_state": None, "evidence_count": 0, "events": [], "turns": [
            {"query": "第一轮问题", "answer": "第一轮报告。", "search_state": None, "state_source": "unavailable", "coverage_score": None, "evidence_count": 0, "skill_generation_id": "old"},
            {"query": "继续核验来源", "answer": "第二轮报告已完成。", "search_state": None, "state_source": "unavailable", "coverage_score": None, "evidence_count": 0, "skill_generation_id": "new"},
        ]}

        def api(route):
            url = route.request.url.split("/api/", 1)[1].split("?", 1)[0]
            if url == "history":
                return route.fulfill(json=[self.item])
            if url == "history/skill-fixture":
                return route.fulfill(json=self.detail)
            if "/skill-generations/" in url:
                which = url.rsplit("/", 1)[1]
                self.counts[which] += 1
                entries = [{"name": "first-run-method" if which == "old" else "source-verification", "category": "strategy", "action": "create", "status": "installed", "description": "按来源逐项核验信息", "reason": "本轮发现来源需要独立核验", "body": "# 本次技能说明\n先读取原始来源，再记录核验结论。"}]
                if which == "new":
                    entries.append({"name": "updated-source-reader", "category": "access", "action": "update", "status": "installed" if self.finished else "running", "description": "支持翻页并保留文章完整链接", "reason": "补充分页覆盖", "body": "## 更新后的说明\n逐页获取，并保留完整 URL。"})
                return route.fulfill(json={"id": which, "status": "completed" if which == "old" or self.finished else "running", "stage": "pipeline", "items": entries, "query": "", "created_at": "", "updated_at": "", "error": ""})
            if route.request.method != "GET":
                return route.abort()
            return route.continue_()

        self.context.route("**/api/**", api)

    def tearDown(self):
        self.context.close()

    def open_conversation(self, mobile=False, width=1440):
        self.page.set_viewport_size({"width": width, "height": 1000})
        self.page.goto(self.url + ("/m?session=skill-fixture" if mobile else "/"), wait_until="networkidle")
        if not mobile:
            self.page.get_by_role("button", name="技能变化测试会话", exact=False).click()
        expect(self.page.get_by_role("region", name="本轮技能变化")).to_have_count(2)

    def check_progress_and_versions(self, mobile=False, width=1440):
        self.open_conversation(mobile, width)
        cards = self.page.get_by_role("region", name="本轮技能变化")
        expect(cards.nth(0).get_by_text("first-run-method", exact=True)).to_be_visible()
        expect(cards.nth(1).get_by_text("first-run-method", exact=True)).to_have_count(0)
        expect(cards.nth(1).get_by_text("正在生成并验证技能…", exact=True)).to_be_visible()
        self.finished = True
        expect(cards.nth(1).get_by_text("已新增 1 个技能，更新 1 个技能。", exact=True)).to_be_visible(timeout=7000)
        cards.nth(1).get_by_text("查看本次版本", exact=True).last.click()
        expect(cards.nth(1).get_by_role("heading", name="更新后的说明")).to_be_visible()
        expect(cards.nth(1).get_by_role("link", name="技能库", exact=True)).to_have_attribute("href", "/m/skills" if mobile else "/skills")
        counts = copy.copy(self.counts)
        self.page.wait_for_timeout(2300)
        self.assertEqual(counts, self.counts, "终态必须停止轮询")
        self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width)
        output = os.environ.get("SEARCHOS_SCREENSHOT_DIR")
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
            cards.nth(1).scroll_into_view_if_needed()
            self.page.screenshot(path=str(Path(output) / f"skill-changes-{'mobile' if mobile else 'desktop'}.png"))
        self.assertFalse(self.errors)

    def test_desktop_progress_and_turn_assignment(self):
        self.check_progress_and_versions()

    def test_mobile_progress_and_reload(self):
        self.check_progress_and_versions(mobile=True, width=390)
        self.page.reload(wait_until="networkidle")
        cards = self.page.get_by_role("region", name="本轮技能变化")
        expect(cards).to_have_count(2)
        expect(cards.nth(1).get_by_text("已新增 1 个技能，更新 1 个技能。", exact=True)).to_be_visible()
        self.page.set_viewport_size({"width": 320, "height": 800})
        self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 320)

    def test_legacy_or_disabled_sessions_have_no_empty_card(self):
        for turn in self.detail["turns"]:
            turn.pop("skill_generation_id")
        self.page.goto(self.url + "/m?session=skill-fixture", wait_until="networkidle")
        expect(self.page.get_by_text("继续核验来源", exact=True)).to_be_visible()
        expect(self.page.get_by_role("region", name="本轮技能变化")).to_have_count(0)
        self.assertEqual(self.counts, {"old": 0, "new": 0})


if __name__ == "__main__":
    unittest.main(verbosity=2)
