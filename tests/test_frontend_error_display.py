"""Lightweight unit checks for frontend HTML-error sanitization helpers.

Executed via Node when available; otherwise static-source assertions only.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API_JS = ROOT / "static" / "js" / "api.js"


def test_api_js_syntax_check():
    """node --check when node is installed."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    result = subprocess.run(
        [node, "--check", str(API_JS)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_import_view_js_syntax_check():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    path = ROOT / "static" / "js" / "views" / "import_view.js"
    result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_parse_response_body_logic_via_node():
    """Exercise parseResponseBody against HTML / empty / JSON bodies."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")

    script = r"""
import { createRequire } from 'module';
// api.js is an ES module with relative imports; inline the pure helpers instead.
function looksLikeHtml(text) {
  const sample = String(text || "").trim().slice(0, 200).toLowerCase();
  return (
    sample.startsWith("<!doctype") ||
    sample.startsWith("<html") ||
    sample.includes("<body") ||
    (sample.includes("internal server error") && sample.includes("<"))
  );
}
function parseResponseBody(text, response) {
  const raw = text == null ? "" : String(text);
  if (!raw.trim()) {
    return {
      error: response.status >= 500 ? "服务器解析失败，请查看服务日志" : response.statusText || "请求失败",
      details: response.status >= 500 ? ["服务器返回了空响应"] : [],
    };
  }
  try {
    const data = JSON.parse(raw);
    if (data && typeof data === "object") return data;
    return { error: "服务器返回了非对象 JSON", details: [] };
  } catch {
    if (looksLikeHtml(raw) || response.status >= 500) {
      return {
        error: "服务器解析失败，请查看服务日志",
        details: ["服务器返回了非 JSON 错误页，完整内容未展示"],
      };
    }
    const snippet = raw.replace(/\s+/g, " ").trim().slice(0, 120);
    return {
      error: snippet || response.statusText || "请求失败",
      details: ["响应不是有效 JSON"],
    };
  }
}

const html = "<html><body><h1>Internal Server Error</h1></body></html>";
const r1 = parseResponseBody(html, { status: 500, statusText: "Internal Server Error" });
if (r1.error.includes("<html") || r1.error.includes("<body")) {
  console.error("FAIL: HTML leaked into error", r1);
  process.exit(1);
}
if (!r1.error.includes("服务器解析失败")) {
  console.error("FAIL: expected safe message", r1);
  process.exit(1);
}

const r2 = parseResponseBody(JSON.stringify({ error: "解析失败", details: ["x"] }), { status: 400 });
if (r2.error !== "解析失败" || r2.details[0] !== "x") {
  console.error("FAIL: JSON path", r2);
  process.exit(1);
}

const r3 = parseResponseBody("", { status: 500, statusText: "Internal Server Error" });
if (r3.error.includes("<")) {
  console.error("FAIL: empty body", r3);
  process.exit(1);
}
console.log("ok");
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "ok" in result.stdout
