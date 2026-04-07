import argparse
import json
import logging
import sys
import time
import datetime
from typing import Any, Optional, cast
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# 禁用日志输出（移除日志功能）
logging.disable(logging.CRITICAL)
logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config.json"

# 常见题干选择器
TITLE_SELECTORS = [
    ".qtitle",
    ".question-title",
    ".div_title",
    ".div_title_question",
    ".field-label",
    ".title",
    ".topic",
    ".label"
]

# 用于查找题干的 JavaScript 代码
FIND_TITLE_JS = f"""
(el) => {{
  const selectors = {json.dumps(TITLE_SELECTORS)};

  function findTitle(root) {{
    for (const sel of selectors) {{
      const node = root.querySelector(sel);
      if (node && node.innerText && node.innerText.trim()) {{
        return node.innerText.trim();
      }}
    }}
    return "";
  }}

  let node = el;
  for (let i = 0; i < 6 && node; i++) {{
    const title = findTitle(node);
    if (title) return title;
    node = node.parentElement;
  }}

  return "";
}}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用 Playwright 自动填写问卷星文本输入框"
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="配置文件路径（默认：config.json）",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="以无头模式运行浏览器",
    )
    return parser.parse_args()


def parse_start_time(start_time_str: Optional[str]) -> Optional[datetime.datetime]:
    """将开始时间字符串解析为 datetime。

    支持的格式：
    - HH:MM 或 HH:MM:SS：仅写时间，按当天该时刻处理
    - YYYY-MM-DD HH:MM 或 YYYY-MM-DD HH:MM:SS：带日期
    - now：立即开始

    如果未传入值，则返回 None。
    """
    if not start_time_str:
        return None

    s = start_time_str.strip()
    if s.lower() == "now":
        return datetime.datetime.now()

    # 依次尝试几种允许的格式
    formats = [
        "%H:%M",
        "%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(s, fmt)
            # If format only contains time, apply today's date
            if fmt in ("%H:%M", "%H:%M:%S"):
                now = datetime.datetime.now()
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
            return dt
        except ValueError:
            continue

    raise ValueError(f"Unsupported start time format: {start_time_str}")


def wait_until(target_dt: datetime.datetime) -> None:
    """阻塞到指定的本地时间。

    如果目标时间已经过去，或者就是当前时间，则直接返回。
    """
    now = datetime.datetime.now()
    seconds = (target_dt - now).total_seconds()
    if seconds <= 0:
        logger.info("开始时间已到或已过，立即开始。")
        return

    logger.info(f"计划开始时间：{target_dt.strftime('%Y-%m-%d %H:%M:%S')}，距离开始还有 {int(seconds)} 秒")

    # 分段睡眠，方便中途中断并定期检查剩余时间
    while True:
        now = datetime.datetime.now()
        remaining = (target_dt - now).total_seconds()
        if remaining <= 0:
            break
        # 每次最多睡眠 60 秒，便于响应中断
        time.sleep(min(60, remaining))

    logger.info("已到达计划时间，开始填写表单。")


def try_click_entry(page, config: dict) -> bool:
    """尝试点击进入问卷的入口按钮或链接。

    返回 True 表示点击成功，返回 False 表示没有找到可点击的入口。

    可选配置项：
    - entry_selectors：要尝试的 CSS 选择器列表
    - entry_texts：要尝试匹配的可见文本列表

    如果都没有配置，则会使用一组常见中文按钮文本作为兜底。
    """
    entry_selectors = config.get("entry_selectors") or []
    entry_texts = config.get("entry_texts") or []

    # 默认尝试的按钮文本
    default_texts = ["立即报名", "立即开始", "报名", "开始填写", "我要报名", "开始答题"]

    # 先按选择器尝试
    for sel in entry_selectors:
        try:
            loc = page.locator(sel)
            cnt = loc.count()
            if cnt <= 0:
                continue
            for i in range(cnt):
                el = loc.nth(i)
                try:
                    if el.is_visible() and el.is_enabled():
                        logger.info(f"Clicking entry selector: {sel}")
                        el.click(timeout=5000)
                        page.wait_for_timeout(1500)
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    # 再按文本尝试
    texts_to_try = entry_texts if entry_texts else default_texts
    for txt in texts_to_try:
        try:
            loc = page.get_by_text(txt)
            cnt = loc.count()
            if cnt <= 0:
                continue
            for i in range(cnt):
                el = loc.nth(i)
                try:
                    if el.is_visible() and el.is_enabled():
                        logger.info(f"Clicking entry text: {txt}")
                        el.click(timeout=5000)
                        page.wait_for_timeout(1500)
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    logger.debug("未找到入口按钮或点击失败")
    return False



def load_config(config_path: str) -> dict:
    """加载配置文件并进行校验。"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"未找到配置文件：{path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件 JSON 无效：{e}")

    # 校验必需字段
    if "url" not in config:
        raise ValueError("配置缺少必需字段：url")

    # 去掉 URL 首尾空白
    config["url"] = config["url"].strip()
    
    return config


def find_question_text(page, input_el) -> str:
    """查找输入框对应的题干文本。"""
    try:
        question_text = input_el.evaluate(FIND_TITLE_JS)
        return question_text.strip() if question_text else ""
    except Exception as e:
        logger.warning(f"提取题干文本失败：{e}")
        return ""


def match_answer(question_text: str, keyword_answers: list) -> Optional[str]:
    """根据题干文本匹配答案。"""
    if not question_text:
        return None
    
    for item in keyword_answers:
        keyword = item.get("keyword", "")
        answer = item.get("answer", "")
        if keyword and keyword in question_text:
            logger.debug(f"匹配到关键字“{keyword}”：{question_text}")
            return answer
    
    return None


def is_input_visible_and_enabled(input_el) -> bool:
    """检查输入框是否可见且可用。"""
    try:
        return input_el.is_visible() and input_el.is_enabled()
    except Exception:
        return False


def main() -> None:
    args = parse_args()
    
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    url = config["url"]
    default_text = config.get("default_text", "默认填写")
    keyword_answers = config.get("keyword_answers", [])
    page_load_timeout = config.get("page_load_timeout", 30000)  # 默认 30 秒
    fill_delay = config.get("fill_delay", 500)  # 每个输入框之间的延迟，单位毫秒
    
    # 如果配置文件中设置了开始时间，就先等待到点再继续执行
    try:
        cfg_start = config.get("start_time")
        start_dt = parse_start_time(cfg_start) if cfg_start else None
    except ValueError as e:
        logger.error(f"配置中的开始时间无效：{e}")
        sys.exit(1)

    if start_dt:
        wait_until(start_dt)

    logger.info(f"正在打开网址：{url}")
    logger.info(f"共读取到 {len(keyword_answers)} 组关键字-答案配置")
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=args.headless,
                channel="chrome"
            )
        except Exception as e:
            logger.error(f"浏览器启动失败：{e}")
            logger.info("提示：请确认已安装 Chrome，或者改用默认的 Chromium")
            sys.exit(1)
        
        context = browser.new_context(
            viewport=cast(Any, {"width": 1920, "height": 1080})
        )
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=page_load_timeout)
            logger.info("页面加载成功")
        except PlaywrightTimeout:
            logger.error(f"页面加载超时：{page_load_timeout} 毫秒")
            browser.close()
            sys.exit(1)
        except Exception as e:
            logger.error(f"页面加载失败：{e}")
            browser.close()
            sys.exit(1)

        # 等待页面进一步稳定
        page.wait_for_timeout(2000)

        # 有些问卷需要先点击“立即报名/立即开始”等入口按钮，先尝试进入
        try:
            clicked = try_click_entry(page, config)
            if clicked:
                logger.info("已点击入口按钮，继续查找填写区域...")
                # 给页面一点时间完成跳转或渲染
                page.wait_for_timeout(1500)
        except Exception as e:
            logger.debug(f"尝试点击入口时发生异常：{e}")

        # 查找所有可填写的文本输入框（包括 text、email、tel、textarea 等）
        input_selector = "input[type='text'], input[type='email'], input[type='tel'], input:not([type]), textarea"
        inputs = page.locator(input_selector)
        count = inputs.count()
        
        logger.info(f"找到 {count} 个输入框")
        
        if count == 0:
            logger.warning("未找到输入框，请检查页面结构。")
            browser.close()
            sys.exit(1)

        filled_count = 0
        skipped_count = 0
        
        for i in range(count):
            input_el = inputs.nth(i)
            
            # 跳过隐藏或不可用的输入框
            if not is_input_visible_and_enabled(input_el):
                logger.debug(f"跳过隐藏或禁用的输入框 #{i+1}")
                skipped_count += 1
                continue
            
            # 获取题干文本
            question_text = find_question_text(page, input_el)
            
            # 根据题干匹配答案
            matched_value = match_answer(question_text, keyword_answers)
            value = matched_value if matched_value is not None else default_text
            
            # 如果匹配到的答案为空字符串，则跳过
            if matched_value == "":
                logger.info(f"输入框 #{i+1}：匹配到空答案，题干：{question_text or '[无题干]'}")
                skipped_count += 1
                continue
            
            try:
                # 填写输入框
                input_el.fill(value)
                filled_count += 1
                            
                if matched_value is not None:
                    logger.info(f"✓ 输入框 #{i+1}：已填写“{value}”，题干：{question_text or '[无题干]'}")
                else:
                    logger.info(f"⚠ 输入框 #{i+1}：未匹配到关键字，已使用默认值，题干：{question_text or '[无题干]'}")
                            
                # 添加一点延迟，避免操作过快
                if fill_delay > 0:
                    page.wait_for_timeout(fill_delay)
                                
            except Exception as e:
                logger.error(f"填写输入框 #{i+1} 失败：{e}")
                skipped_count += 1

        logger.info(f"\n{'='*50}")
        logger.info(f"统计：已填写 {filled_count} 个，已跳过 {skipped_count} 个，共 {count} 个")
        logger.info(f"{'='*50}")

        # 提示用户可以手动提交
        logger.info("\n表单已自动填写完成，你可以检查后手动提交。")
        logger.info("如需自动提交，可以自行补充提交按钮逻辑。")
        
        # 保持浏览器打开一小段时间，方便检查填写结果
        logger.info("浏览器将在 10 秒后关闭（按 Ctrl+C 可立即关闭）")
        try:
            page.wait_for_timeout(10000)
        except KeyboardInterrupt:
            logger.info("正在关闭浏览器...")
        finally:
            browser.close()
            logger.info("完成。")


if __name__ == "__main__":
    main()
