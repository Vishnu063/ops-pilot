"""Real Chromium dashboard acceptance; Docker is the existing simulated fixture.

Run explicitly with Playwright installed. The separate Docker lab tests actual
container mutations; this script tests real browser/session/UI behavior.
"""
from pathlib import Path
import json
import os
import sys
import threading

# Reuse the existing real HTTP/SQLite fixture rather than creating a second engine.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pilot import PilotTests, ProbeHandler
from ops_pilot.web import Server
from playwright.sync_api import sync_playwright, expect

OUTPUT = Path("browser-evidence")
OUTPUT.mkdir(exist_ok=True)


def run():
    fixture = PilotTests(methodName="test_repair_requires_separate_approval_and_replay_is_refused")
    fixture.setUp()
    server = None
    try:
        ProbeHandler.status = 503
        fixture.pilot.tick()
        server = Server(fixture.pilot, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        errors = []
        with sync_playwright() as playwright:
            options = {}
            if os.environ.get('OPS_PILOT_CHROMIUM'):
                options.update(executable_path=os.environ['OPS_PILOT_CHROMIUM'], args=[
                    '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
                    '--no-zygote', '--use-gl=angle',
                    '--use-angle=swiftshader', '--disable-features=Vulkan'])
            browser = playwright.chromium.launch(**options)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            assert context.request.get(origin + "/api/state").status == 401
            page.goto(origin + "/login?token=" + server.token)
            expect(page.locator("#app-name")).to_have_text("Test application")
            expect(page.locator("#health-status")).to_have_text("Endpoint needs attention")
            assert not fixture.adapter.mutations
            page.locator("#plan").click()
            expect(page.locator("#plan-panel")).to_be_visible()
            plan_id = page.locator("#plan-id").inner_text()
            assert len(plan_id) == 32
            assert fixture.adapter.current_id in page.locator("#command").inner_text()
            expect(page.locator("#approve")).to_be_disabled()
            page.locator("#confirm-id").fill("wrong-id")
            expect(page.locator("#approve")).to_be_disabled()
            page.locator("#confirm-id").fill(plan_id)
            expect(page.locator("#approve")).to_be_enabled()
            page.locator("#approve").click()
            expect(page.locator("#plan-status")).to_have_text("approved")
            assert not fixture.adapter.mutations, "Approval alone must not mutate Docker"
            page.screenshot(path=str(OUTPUT / "desktop-approved.png"), full_page=True)
            ProbeHandler.status = 200
            page.locator("#apply").click()
            expect(page.locator("#result-status")).to_have_text("Recovery checks passed", timeout=15000)
            assert len(fixture.adapter.mutations) == 1
            expect(page.locator("#apply")).to_be_hidden()
            page.reload()
            expect(page.locator("#plan-status")).to_have_text("verified")
            expect(page.locator("#apply")).to_be_hidden()
            assert len(fixture.adapter.mutations) == 1, "Refreshing must not replay a repair"
            page.locator("#monitor").click()
            expect(page.locator("#monitor-label")).to_have_text("Monitoring paused")
            page.locator("#monitor").click()
            expect(page.locator("#monitor-label")).to_have_text("Monitoring on")
            page.locator("#maintenance").click()
            expect(page.locator("#monitor-label")).to_contain_text("Maintenance until")
            expect(page.locator("#plan")).to_be_disabled()
            page.reload()
            expect(page.locator("#maintenance")).to_have_text("End maintenance")
            page.locator("#maintenance").click()
            expect(page.locator("#monitor-label")).to_have_text("Monitoring on")
            expect(page.locator("#diagnosis-detail")).to_contain_text("State: running")
            with page.expect_download() as download:
                page.get_by_role("link", name="Download incident report (JSON)").click()
            report_path = OUTPUT / "downloaded-report.json"
            download.value.save_as(report_path)
            report = json.loads(report_path.read_text())
            assert report["result"]["status"] == "verified"
            assert server.token not in report_path.read_text()
            expect(page.locator("#alerts")).to_contain_text("repair verified")
            page.screenshot(path=str(OUTPUT / "desktop-recovered.png"), full_page=True)
            # Hostile labels render as text, not markup or executable elements.
            fixture.pilot.config["name"] = '<img src=x onerror="alert(1)">'
            page.reload()
            expect(page.locator("#app-name")).to_have_text(fixture.pilot.config["name"])
            assert page.locator("#app-name img").count() == 0
            fixture.pilot.config["name"] = "Test application"
            page.reload()
            page.set_viewport_size({"width": 390, "height": 844})
            expect(page.locator("#health-status")).to_have_text("Endpoint checks passed")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile horizontal overflow"
            page.screenshot(path=str(OUTPUT / "mobile-recovered.png"), full_page=True)
            # A second browser has no inherited session. No API/controls are exposed.
            stranger = browser.new_context()
            assert stranger.request.get(origin + "/api/state").status == 401
            stranger.close()
            assert not errors, errors
            context.close()
            browser.close()
        (OUTPUT / "result.json").write_text(json.dumps({
            "status": "passed", "browser": "Chromium", "viewports": ["1280x900", "390x844"],
            "checks": ["session required", "incident displayed", "exact-plan approval", "approval is non-mutating",
                       "explicit execution", "verified recovery display", "reload does not replay", "pause/resume",
                       "maintenance reload and repair block", "authenticated report download", "local alert display", "label escaping", "no horizontal overflow", "no JavaScript errors"],
            "scope": "Real browser/HTTP/SQLite; simulated Docker. Actual Docker tested separately."}, indent=2))
        print("Browser acceptance passed: desktop, mobile, session, approval, recovery, no replay or script errors.")
    finally:
        if server:
            server.shutdown()
            server.server_close()
            thread.join()
        fixture.tearDown()


if __name__ == "__main__":
    run()
