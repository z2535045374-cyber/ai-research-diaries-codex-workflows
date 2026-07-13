#!/usr/bin/env python3
"""Real-browser meeting-state tests driven through ``playwright-cli``."""

from __future__ import annotations

import functools
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
BUILDER = SKILL_ROOT / "scripts" / "build_briefing.py"


def sanitised_payload() -> dict[str, Any]:
    return {
        "project_title": "Sanitised browser fixture",
        "recent_progress": ["Prepared a de-identified progress summary."],
        "completed_work": ["Checked the sanitised transcript set."],
        "key_findings": ["The fixture contains no participant details."],
        "unresolved_questions": ["Should the coding frame be extended?"],
        "decisions_required": ["Agree the next analysis checkpoint."],
        "next_actions": ["Draft the revised coding frame."],
        "timeline": ["Review the draft at the next meeting."],
    }


def locate_browser_tool() -> tuple[str | None, dict[str, str], str]:
    environment = os.environ.copy()
    cli = shutil.which("playwright-cli", path=environment.get("PATH"))
    if cli is None:
        return None, environment, "playwright-cli is absent from PATH"

    if shutil.which("node", path=environment.get("PATH")) is None:
        return None, environment, "playwright-cli is present but node is absent from PATH"

    probe = subprocess.run(
        [cli, "--version"],
        cwd=SKILL_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if probe.returncode != 0:
        reason = (probe.stderr or probe.stdout).strip()
        raise RuntimeError(f"playwright-cli was found but cannot start: {reason}")
    return cli, environment, ""


class QuietRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        """Keep the executable test output focused on assertions."""


BROWSER_WORKFLOW = r"""async page => {
  const assert = (condition, message) => {
    if (!condition) {
      throw new Error(message);
    }
  };
  const exportPath = __EXPORT_PATH_JSON__;
  const invalidImportPaths = __INVALID_IMPORT_PATHS_JSON__;
  const pageErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.reload();
  await page.waitForLoadState("domcontentloaded");

  const questionId = "unresolved_questions-1";
  const decisionId = "decisions_required-1";
  const actionId = "next_actions-1";
  const question = page.locator('[data-state-id="' + questionId + '"]');
  const decision = page.locator('[data-state-id="' + decisionId + '"]');
  const action = page.locator('[data-state-id="' + actionId + '"]');
  const importInput = page.locator("#import-state");
  const message = page.locator("#state-message");

  const readControls = async () => ({
    discussed: await question.locator('[data-state-control="discussed"]').isChecked(),
    questionNote: await question.locator('[data-state-control="note"]').inputValue(),
    decisionStatus: await decision.locator('[data-state-control="status"]').inputValue(),
    decisionNote: await decision.locator('[data-state-control="note"]').inputValue(),
    completed: await action.locator('[data-state-control="completed"]').isChecked(),
    actionNote: await action.locator('[data-state-control="note"]').inputValue()
  });

  assert(await page.evaluate(() => window.localStorage.length) === 0, "Unexpected initial local storage");
  await question.locator('[data-state-control="discussed"]').check();
  await question.locator('[data-state-control="note"]').fill("Discussed with the supervisory team.");
  await decision.locator('[data-state-control="status"]').selectOption("agreed");
  await decision.locator('[data-state-control="note"]').fill("Checkpoint agreed.");
  await action.locator('[data-state-control="completed"]').check();
  await action.locator('[data-state-control="note"]').fill("Draft completed.");

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", {name: "Export state"}).click();
  const download = await downloadPromise;
  assert(download.suggestedFilename() === "supervisor-meeting-state.json", "Unexpected export filename");
  await download.saveAs(exportPath);

  await page.getByRole("button", {name: "Reset state"}).click();
  await message.waitFor({state: "visible"});
  assert(await message.textContent() === "Meeting state reset.", "Reset status was not announced");
  const reset = await readControls();
  assert(reset.discussed === false && reset.questionNote === "", "Question state was not reset");
  assert(reset.decisionStatus === "pending" && reset.decisionNote === "", "Decision state was not reset");
  assert(reset.completed === false && reset.actionNote === "", "Action state was not reset");

  await importInput.setInputFiles(exportPath);
  await page.waitForFunction(() => document.getElementById("state-message").textContent === "Meeting state imported.");
  const restored = await readControls();
  assert(restored.discussed === true && restored.questionNote === "Discussed with the supervisory team.", "Question state was not restored");
  assert(restored.decisionStatus === "agreed" && restored.decisionNote === "Checkpoint agreed.", "Decision state was not restored");
  assert(restored.completed === true && restored.actionNote === "Draft completed.", "Action state was not restored");
  const stableState = JSON.stringify(restored);

  const assertRejectedAtomically = async path => {
    await message.evaluate(element => {
      element.textContent = "";
      element.dataset.kind = "";
      element.setAttribute("role", "status");
    });
    await importInput.setInputFiles(path);
    await page.waitForFunction(() => {
      const element = document.getElementById("state-message");
      return element.dataset.kind === "error" && element.textContent.length > 0;
    });
    assert(await message.getAttribute("role") === "alert", path + " did not report an accessible error");
    assert(JSON.stringify(await readControls()) === stableState, path + " changed meeting controls");
  };

  for (const path of invalidImportPaths) {
    await assertRejectedAtomically(path);
  }
  assert(await page.evaluate(() => window.localStorage.length) === 0, "The workspace wrote to local storage");
  assert(pageErrors.length === 0, "Page errors: " + pageErrors.join("; "));
  return {result: "PASS", invalidImportsRejectedAtomically: 7, exportResetRestore: true};
}"""


WORKSPACE_INTERACTION_WORKFLOW = r"""async page => {
  const assert = (condition, message) => {
    if (!condition) {
      throw new Error(message);
    }
  };
  const pageErrors = [];
  const externalRequests = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  page.on("console", message => {
    if (message.type() === "error") {
      pageErrors.push(message.text());
    }
  });
  page.on("request", request => {
    if (!request.url().startsWith(page.url().split("/").slice(0, 3).join("/"))) {
      externalRequests.push(request.url());
    }
  });
  await page.setViewportSize({width: 1280, height: 900});
  await page.reload();
  await page.waitForLoadState("domcontentloaded");

  const groups = page.locator(".workspace-group");
  assert(await groups.count() === 4, "The four workspace groups were not rendered");
  assert(await page.locator(".overview-counts dd").count() === 7, "Mechanical counts are incomplete");

  const discussionLink = page.locator('[data-nav-group="discussion"]');
  await discussionLink.click();
  assert(await discussionLink.getAttribute("aria-current") === "location", "Desktop navigation did not activate the selected group");

  const search = page.locator("#workspace-search");
  await search.fill("coding frame");
  assert(await page.locator('[data-state-id="unresolved_questions-1"]').isVisible(), "Search hid a matching item");
  assert(await page.locator('[data-field="completed_work"]').isHidden(), "Search retained a non-matching section");
  await search.fill("");
  assert(await page.locator('[data-field="completed_work"]').isVisible(), "Clearing search did not restore content");

  await page.locator("#collapse-all").click();
  assert(await groups.evaluateAll(elements => elements.every(element => !element.open)), "Collapse all did not close every group");
  await page.locator("#expand-all").click();
  assert(await groups.evaluateAll(elements => elements.every(element => element.open)), "Expand all did not open every group");

  await page.setViewportSize({width: 390, height: 844});
  const mobileNavigation = page.locator("#mobile-group-nav");
  await mobileNavigation.selectOption("discussion");
  assert(await page.locator("#group-discussion").getAttribute("open") !== null, "Mobile navigation did not open the target group");
  assert(await page.evaluate(() => document.activeElement?.closest("#group-discussion") !== null), "Mobile navigation did not move focus to the target group");
  assert(await page.evaluate(() => document.documentElement.scrollWidth === innerWidth), "The mobile layout overflows horizontally");
  const mobileToolGap = await page.evaluate(() => {
    const searchBox = document.getElementById("workspace-search").getBoundingClientRect();
    const expandBox = document.getElementById("expand-all").getBoundingClientRect();
    return expandBox.top - searchBox.bottom;
  });
  assert(mobileToolGap < 48, "The mobile search control reserves excessive vertical space");
  const mobileTrailingGap = await page.evaluate(() => {
    const toolsBox = document.querySelector(".workspace-tools").getBoundingClientRect();
    const messageBox = document.getElementById("state-message").getBoundingClientRect();
    return toolsBox.bottom - messageBox.bottom;
  });
  assert(mobileTrailingGap < 48, "The mobile state message reserves excessive vertical space");

  const question = page.locator('[data-state-id="unresolved_questions-1"]');
  await question.locator('[data-state-control="discussed"]').check();
  await question.locator('[data-state-control="note"]').fill("Discuss next steps.");
  await page.locator("#group-overview").evaluate(element => { element.open = false; });
  await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
  assert(await groups.evaluateAll(elements => elements.every(element => element.open)), "Print preparation did not expand every group");
  assert((await question.locator(".print-state").textContent()).includes("Discussed: Yes"), "Print state omitted the current question status");
  assert((await question.locator(".print-state").textContent()).includes("Discuss next steps."), "Print state omitted the current meeting note");
  await page.emulateMedia({media: "print"});
  assert(await question.locator(".print-state").evaluate(element => getComputedStyle(element).display !== "none"), "Print state is hidden in print media");
  await page.emulateMedia({media: "screen"});
  await page.evaluate(() => window.dispatchEvent(new Event("afterprint")));
  assert(await page.locator("#group-overview").getAttribute("open") === null, "Print cleanup did not restore the earlier open state");

  await search.focus();
  const focusIsVisible = await search.evaluate(element => {
    const style = getComputedStyle(element);
    return style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0;
  });
  assert(focusIsVisible, "Keyboard focus is not visibly styled");

  const browser = page.context().browser();
  assert(browser !== null, "The browser context is unavailable");
  const noScriptContext = await browser.newContext({javaScriptEnabled: false});
  const noScriptPage = await noScriptContext.newPage();
  await noScriptPage.goto(page.url().split("#")[0], {waitUntil: "load"});
  assert(await noScriptPage.locator("html.js").count() === 0, "The no-script page retained the JavaScript marker");
  assert(await noScriptPage.locator(".workspace-group").count() === 4, "The no-script page omitted workspace groups");
  assert(await noScriptPage.locator(".item-list > li").count() === 7, "The no-script page omitted supplied research items");
  assert(await noScriptPage.locator(".no-script-message").isVisible(), "The no-script explanation is not visible");
  await noScriptContext.close();

  assert(await page.evaluate(() => window.localStorage.length) === 0, "The workspace wrote to local storage");
  assert(externalRequests.length === 0, "External requests: " + externalRequests.join("; "));
  assert(pageErrors.length === 0, "Page errors: " + pageErrors.join("; "));
  return {result: "PASS", navigation: true, search: true, collapse: true, print: true, mobile: true};
}"""


class BrowserMeetingStateTests(unittest.TestCase):
    """Exercise state import/export in a real Chromium browser."""

    def setUp(self) -> None:
        cli, environment, reason = locate_browser_tool()
        if cli is None:
            self.skipTest(f"Real-browser test skipped: {reason}")
        self.cli = cli
        self.environment = environment
        self.session = f"briefing-state-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.work = Path(self.temporary_directory.name)

        payload = sanitised_payload()
        input_path = self.work / "sanitised-briefing.json"
        output_path = self.work / "sanitised-briefing.html"
        input_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        build = subprocess.run(
            [sys.executable, str(BUILDER), str(input_path), str(output_path)],
            cwd=SKILL_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(build.returncode, 0, build.stderr)

        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        brief_id = hashlib.sha256(canonical).hexdigest()
        valid_state = {
            "schema_version": 1,
            "brief_id": brief_id,
            "exported_at": "2026-07-14T12:00:00.000Z",
            "questions": {
                "unresolved_questions-1": {
                    "discussed": True,
                    "note": "Discussed with the supervisory team.",
                }
            },
            "decisions": {
                "decisions_required-1": {
                    "status": "agreed",
                    "note": "Checkpoint agreed.",
                }
            },
            "actions": {
                "next_actions-1": {
                    "completed": True,
                    "note": "Draft completed.",
                }
            },
        }
        self.export_path = self.work / "exported-state.json"
        self.invalid_import_paths = self._write_invalid_imports(valid_state)

        handler = functools.partial(
            QuietRequestHandler,
            directory=str(self.work),
        )
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.server_thread.start()
        self.addCleanup(self._stop_server)

        port = self.server.server_address[1]
        self.addCleanup(self._close_browser)
        open_result = self._run_cli(
            "open",
            f"http://127.0.0.1:{port}/{output_path.name}",
        )
        self.assertNotIn("### Error", open_result)

    def _write_invalid_imports(self, valid_state: dict[str, Any]) -> list[Path]:
        paths: list[Path] = []

        def write_json(name: str, state: dict[str, Any]) -> None:
            path = self.work / name
            path.write_text(
                json.dumps(state, ensure_ascii=False),
                encoding="utf-8",
            )
            paths.append(path)

        malformed = self.work / "malformed-json.json"
        malformed.write_text("{not valid JSON", encoding="utf-8")
        paths.append(malformed)

        wrong_brief = json.loads(json.dumps(valid_state))
        wrong_brief["brief_id"] = "0" * 64
        write_json("wrong-brief-id.json", wrong_brief)

        unknown_id = json.loads(json.dumps(valid_state))
        unknown_id["questions"]["unresolved_questions-999"] = {
            "discussed": False,
            "note": "",
        }
        write_json("unknown-id.json", unknown_id)

        wrong_boolean = json.loads(json.dumps(valid_state))
        wrong_boolean["questions"]["unresolved_questions-1"]["discussed"] = "true"
        write_json("wrong-boolean.json", wrong_boolean)

        invalid_status = json.loads(json.dumps(valid_state))
        invalid_status["decisions"]["decisions_required-1"]["status"] = "complete"
        write_json("invalid-decision-status.json", invalid_status)

        overlong_note = json.loads(json.dumps(valid_state))
        overlong_note["actions"]["next_actions-1"]["note"] = "x" * 5001
        write_json("overlong-note.json", overlong_note)

        oversized = self.work / "oversized-file.json"
        oversized.write_bytes(b" " * 262145)
        paths.append(oversized)
        return paths

    def _run_cli(self, *arguments: str, raw: bool = False) -> str:
        command = [self.cli]
        if raw:
            command.append("--raw")
        command.extend((f"-s={self.session}", *arguments))
        result = subprocess.run(
            command,
            cwd=self.work,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        combined = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, combined)
        self.assertNotIn("### Error", combined)
        return combined

    def _close_browser(self) -> None:
        subprocess.run(
            [self.cli, f"-s={self.session}", "close"],
            cwd=self.work,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=5)

    def test_export_reset_restore_and_invalid_imports_are_atomic(self) -> None:
        workflow = BROWSER_WORKFLOW.replace(
            "__EXPORT_PATH_JSON__",
            json.dumps(str(self.export_path)),
        ).replace(
            "__INVALID_IMPORT_PATHS_JSON__",
            json.dumps([str(path) for path in self.invalid_import_paths]),
        )
        output = self._run_cli("run-code", workflow, raw=True)

        self.assertIn("PASS", output)
        self.assertIn("invalidImportsRejectedAtomically", output)
        exported_text = self.export_path.read_text(encoding="utf-8")
        exported = json.loads(exported_text)
        self.assertEqual(exported["schema_version"], 1)
        self.assertTrue(exported["questions"]["unresolved_questions-1"]["discussed"])
        self.assertEqual(
            exported["decisions"]["decisions_required-1"]["status"],
            "agreed",
        )
        self.assertTrue(exported["actions"]["next_actions-1"]["completed"])
        self.assertNotIn("Sanitised browser fixture", exported_text)
        self.assertNotIn("Should the coding frame be extended?", exported_text)

    def test_navigation_search_collapse_print_and_mobile_workflow(self) -> None:
        output = self._run_cli(
            "run-code",
            WORKSPACE_INTERACTION_WORKFLOW,
            raw=True,
        )

        self.assertIn("PASS", output)
        self.assertIn('"navigation":true', output)
        self.assertIn('"search":true', output)
        self.assertIn('"collapse":true', output)
        self.assertIn('"print":true', output)
        self.assertIn('"mobile":true', output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
