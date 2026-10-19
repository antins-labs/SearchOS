"""输入焦点回归：启动前端后，用已安装 Playwright 的 Python 运行本文件。

SEARCHOS_TEST_URL=http://127.0.0.1:3001 .venv/bin/python web/frontend/tests/focus-styles.browser.py
"""

import os
import unittest

from playwright.sync_api import expect, sync_playwright


class FocusStylesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.url = os.environ.get("SEARCHOS_TEST_URL", "http://127.0.0.1:3001")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        # 测试只打开界面，不允许提交研究、修改设置或保存计划。
        self.context.route("**/api/**", lambda route: route.continue_()
                           if route.request.method == "GET" else route.abort())

    def tearDown(self):
        self.context.close()

    def open(self, path="/", width=1440, theme="light"):
        self.page.set_viewport_size({"width": width, "height": 1000})
        self.page.goto(self.url + path, wait_until="networkidle")
        self.page.evaluate("theme => document.documentElement.classList.toggle('dark', theme === 'dark')", theme)

    def assert_focus_surface(self, field, shell):
        self.page.evaluate("document.activeElement?.blur()")
        before = shell.evaluate("e => getComputedStyle(e).borderColor")
        field.focus()
        self.assertEqual(field.evaluate("e => getComputedStyle(e).outlineStyle"), "none")
        self.page.wait_for_function(
            "({element, border}) => getComputedStyle(element).borderColor !== border",
            arg={"element": shell.element_handle(), "border": before}, timeout=3000,
        )
        self.assertNotEqual(shell.evaluate("e => getComputedStyle(e).borderColor"), before)
        self.assertGreater(float(shell.evaluate("e => parseFloat(getComputedStyle(e).borderRadius)")), 0)

    def test_research_composer_across_breakpoints_and_themes(self):
        for width in (1440, 768, 390, 320):
            for theme in ("light", "dark"):
                with self.subTest(width=width, theme=theme):
                    self.open(width=width, theme=theme)
                    field = self.page.get_by_role("textbox", name="Research question")
                    self.assert_focus_surface(field, self.page.locator(".research-composer-form"))
                    field.fill("帮我整理今天值得关注的 AI 新闻，附上原始来源和简短解读。\n再列出来源。")
                    self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width)

    def test_history_search_and_keyboard_buttons(self):
        self.open()
        field = self.page.get_by_role("textbox", name="Search research history")
        field.focus()
        self.assertEqual(field.evaluate("e => getComputedStyle(e).outlineStyle"), "none")
        self.page.get_by_role("button", name="Edit table schema").focus()
        self.page.keyboard.press("Tab")
        self.assertEqual(self.page.locator(":focus").get_attribute("aria-label"), "Run overrides")
        self.assertEqual(self.page.locator(":focus").evaluate("e => getComputedStyle(e).outlineStyle"), "solid")

    def test_mobile_composer_and_task_search(self):
        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                self.open("/m", width=390, theme=theme)
                field = self.page.get_by_role("textbox", name="交办任务")
                self.assert_focus_surface(field, field.locator(".."))
                # 输入框聚焦会隐藏底栏；先收起键盘状态。
                field.blur()
                self.page.get_by_role("button", name="任务", exact=True).click()
                field = self.page.get_by_role("textbox", name="搜索任务")
                self.assert_focus_surface(field, field.locator(".."))

    def test_mobile_material_search_and_plan_fields(self):
        self.open("/m", width=390)
        self.page.get_by_role("button", name="添加资料", exact=True).click()
        field = self.page.get_by_role("textbox", name="搜索资料", exact=True)
        self.assert_focus_surface(field, field.locator(".."))
        self.page.keyboard.press("Escape")
        self.page.get_by_role("button", name="让好信息，按时到来", exact=False).click()
        expect(self.page.get_by_role("button", name="关闭安排定时简报")).to_be_focused()
        for label in ("计划名称", "让助理做什么", "执行时间", "时区", "重复频率"):
            with self.subTest(field=label):
                field = self.page.get_by_label(label, exact=False)
                self.assert_focus_surface(field, field)
        checkbox = self.page.get_by_role("checkbox", name="启用自动执行", exact=False)
        self.page.get_by_role("spinbutton", name="最长执行", exact=False).focus()
        self.page.keyboard.press("Tab")
        expect(checkbox).to_be_focused()
        self.assertEqual(checkbox.evaluate("e => getComputedStyle(e).outlineStyle"), "solid")

    def test_conversation_composer(self):
        item = {"session_id": "focus-fixture", "title": "焦点回归会话", "status": "completed",
                "coverage_score": None, "updated_at": 1, "project": "", "tags": [],
                "favorite": False, "archived": False}
        detail = {**item, "query": item["title"], "answer": "已完成的研究。", "turns": [],
                  "search_state": None, "evidence_count": 0, "events": []}
        self.page.route("**/api/history", lambda route: route.fulfill(json=[item]))
        self.page.route("**/api/history/focus-fixture", lambda route: route.fulfill(json=detail))
        self.open()
        self.page.get_by_role("button", name="焦点回归会话", exact=False).click()
        expect(self.page.get_by_text("已完成的研究。", exact=True)).to_be_visible()
        self.assert_focus_surface(self.page.get_by_role("textbox", name="Research question"),
                                  self.page.locator(".research-composer-form"))

    def test_schema_settings_and_skill_inputs(self):
        self.open()
        self.page.get_by_role("button", name="Edit table schema").click()
        field = self.page.get_by_placeholder("Tesla, BYD, NIO")
        self.assert_focus_surface(field, field.locator(".."))
        self.open("/settings")
        field = self.page.get_by_role("textbox", name="搜索 Middleware")
        self.assert_focus_surface(field, field.locator(".."))
        field = self.page.locator("input.surface:enabled").first
        self.assert_focus_surface(field, field)
        for path, width in (("/skills", 1440), ("/m/skills", 390)):
            self.open(path, width=width)
            field = self.page.get_by_role("textbox", name="查询技能")
            self.assert_focus_surface(field, field.locator(".."))
        self.open("/m/skills/new", width=390)
        field = self.page.get_by_placeholder("https://github.com")
        self.assert_focus_surface(field, field)


if __name__ == "__main__":
    unittest.main(verbosity=2)
