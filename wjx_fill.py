import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_CONFIG_PATH = "config.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-fill WJX text inputs with Playwright"
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Config file path (default: config.json)",
    )
    return parser.parse_args()


def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    url = config.get("url")
    default_text = config.get("default_text", "默认填写")
    keyword_answers = config.get("keyword_answers", [])

    if not url:
        raise ValueError("Config missing 'url'")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded")

        # 等待页面加载
        page.wait_for_timeout(1000)

        # 选择所有可填写的文本输入（文本框、textarea）
        inputs = page.locator("input[type='text'], textarea")
        count = inputs.count()

        for i in range(count):
            input_el = inputs.nth(i)
            question_text = input_el.evaluate(
                """
                (el) => {
                  const selectors = [
                    ".qtitle",
                    ".question-title",
                    ".div_title",
                    ".div_title_question",
                    ".field-label",
                    ".title",
                    ".topic",
                    ".label"
                  ];

                  function findTitle(root) {
                    for (const sel of selectors) {
                      const node = root.querySelector(sel);
                      if (node && node.innerText && node.innerText.trim()) {
                        return node.innerText.trim();
                      }
                    }
                    return "";
                  }

                  let node = el;
                  for (let i = 0; i < 6 && node; i++) {
                    const title = findTitle(node);
                    if (title) return title;
                    node = node.parentElement;
                  }

                  return "";
                }
                """
            )

            matched_value = None
            for item in keyword_answers:
                keyword = item.get("keyword", "")
                answer = item.get("answer", "")
                if keyword and keyword in question_text:
                    matched_value = answer
                    break

            value = matched_value if matched_value is not None else default_text
            input_el.fill(value)

            if matched_value is None:
                print(f"未匹配题干：{question_text or '[无题干]'}，已填默认值")

        # 你可以取消注释以提交（确保授权）
        # page.locator("a#submit_button, input#submit_button, button#submit_button").click()

        # 保持浏览器打开方便检查
        page.wait_for_timeout(3000)
        browser.close()


if __name__ == "__main__":
    main()
