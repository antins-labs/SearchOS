"""No-cost container checks: storage, headless Chromium, isolated skill execution."""
import asyncio
import json
from pathlib import Path
import tempfile
import urllib.request


async def check():
    report = {}
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=5) as reply:
            report["api"] = "ok" if reply.status == 200 else "failed"
        with tempfile.TemporaryFile(dir="/data") as stream:
            stream.write(b"storage probe")
        report["storage"] = "ok"
    except Exception as error:
        report["service_error"] = type(error).__name__
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content("<title>SearchOS check</title>")
                assert await page.title() == "SearchOS check"
                report["browser"] = "ok"
            finally:
                await browser.close()
    except Exception as error:
        report["browser"] = "failed: " + type(error).__name__
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    from searchos.skills.runtime.command_runtime import run_command
    with tempfile.TemporaryDirectory(prefix="searchos-doctor-") as directory:
        root = Path(directory)
        skill = root / "skill"
        skill.mkdir()
        (skill / "probe.py").write_text("print('searchos-isolated-probe')")
        result = await run_command(skill, ["python", "probe.py"],
                                   work_dir=root / "work", execution_dir=root / "records",
                                   network=False, timeout_s=10)
        ready = result["status"] == "completed" and result["stdout"].strip() == "searchos-isolated-probe"
        report["skill_sandbox"] = "ok" if ready else "unavailable"
        if not ready:
            report["skill_sandbox_detail"] = result.get("error") or result.get("stderr", "")
            report["action"] = "技能脚本不可用。保留隔离限制，先用内置搜索/读取；不要改为 privileged 或关闭沙箱。"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check()))
