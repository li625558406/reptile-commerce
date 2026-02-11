"""
Newegg 商品爬虫脚本
基于 Playwright 的异步爬虫，用于抓取 Newegg 分类页面商品数据
"""

import asyncio
import json
import random
import re
from datetime import datetime
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page, Browser, Locator


# ==================== 配置区域 ====================
# 在此处添加要抓取的分类链接
TARGET_URLS = [
    "https://www.newegg.com/p/pl?Submit=StoreIM&Depa=1",
    "https://www.newegg.com/p/pl?Submit=StoreIM&Depa=2",
    "https://www.newegg.com/p/pl?Submit=StoreIM&Depa=3",
    "https://www.newegg.com/p/pl?Submit=StoreIM&Depa=5",
    "https://www.newegg.com/p/pl?Submit=StoreIM&Depa=6",
    "https://www.newegg.com/p/pl?Submit=StoreIM&Depa=8",
    "https://www.newegg.com/p/pl?Submit=StoreIM&Depa=9",
    "https://www.newegg.com/p/pl?Submit=StoreIM&Depa=10",
    "https://www.newegg.com/p/pl?Submit=StoreIM&Depa=13",
    "https://www.newegg.com/p/pl?Submit=StoreIM&Depa=15",
    "https://www.newegg.com/p/pl?Submit=StoreIM&Depa=16",
    # "https://www.newegg.com/Video-Cards/Video-Card-Series/ID-1805",
    # 添加更多 URL...
]

# 最大抓取页数（防止无限抓取）
MAX_PAGES = 10

# User-Agent 模拟真实浏览器
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# 随机等待范围（秒）
MIN_WAIT = 2
MAX_WAIT = 5


# ==================== 数据解析函数 ====================

async def extract_price(price_element: Optional[Locator]) -> str:
    """
    提取价格，去除逗号和 $ 符号
    如果没有价格则返回 "0"
    """
    if not price_element:
        return "0"

    try:
        price_text = await price_element.inner_text()
        # 移除 $ 符号和逗号
        price_clean = price_text.replace("$", "").replace(",", "").strip()
        # 验证是否为有效价格
        if re.match(r'^\d+\.?\d*$', price_clean):
            return price_clean
        return "0"
    except Exception:
        return "0"


async def extract_item_features(item_cell: Locator) -> List[str]:
    """
    提取商品特性列表 (ul.item-features 下的所有 li 文本)
    """
    features = []
    try:
        features_ul = item_cell.locator("ul.item-features")
        if await features_ul.count() > 0:
            feature_items = features_ul.locator("li")
            count = await feature_items.count()
            for i in range(count):
                try:
                    feature_text = await feature_items.nth(i).inner_text()
                    if feature_text.strip():
                        features.append(feature_text.strip())
                except Exception:
                    continue
    except Exception:
        pass
    return features


async def parse_product_item(item_cell: Locator) -> Optional[Dict]:
    """
    解析单个商品卡片
    返回商品信息字典，解析失败返回 None
    """
    try:
        # 提取商品标题
        title_element = item_cell.locator(".item-title").first
        title = await title_element.inner_text() if await title_element.count() > 0 else ""

        # 提取价格
        price_element = item_cell.locator(".price-current strong").first
        price = await extract_price(price_element if await price_element.count() > 0 else None)

        # 提取商品图片
        img_element = item_cell.locator(".item-img img").first
        img_url = ""
        if await img_element.count() > 0:
            img_url = await img_element.get_attribute("src") or ""

        # 提取商品特性列表
        item_features = await extract_item_features(item_cell)

        # 提取商品详情链接
        link_element = item_cell.locator(".item-title").first
        product_link = ""
        if await link_element.count() > 0:
            href = await link_element.get_attribute("href")
            product_link = href if href and href.startswith("http") else f"https://www.newegg.com{href}" if href else ""

        # 构建商品数据
        product_data = {
            "title": title.strip(),
            "price": price,
            "img_url": img_url,
            "item_features": item_features,
            "product_link": product_link,
        }

        return product_data

    except Exception as e:
        print(f"  ⚠️  解析单个商品失败: {e}")
        return None


async def scrape_page(page: Page, url: str, page_num: int) -> List[Dict]:
    """
    抓取单页数据
    """
    print(f"\n📄 正在抓取第 {page_num} 页: {url}")

    products = []

    try:
        # 导航到目标页面
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # 等待商品列表加载
        await page.wait_for_selector(".item-cell", timeout=15000)

        # 获取所有商品卡片
        item_cells = page.locator(".item-cell")
        count = await item_cells.count()
        print(f"  📦 找到 {count} 个商品")

        # 遍历解析每个商品
        for i in range(count):
            item_cell = item_cells.nth(i)
            product = await parse_product_item(item_cell)
            if product:
                products.append(product)
                print(f"    ✓ [{i+1}/{count}] {product['title'][:50]}...")

        print(f"  ✅ 第 {page_num} 页完成，成功解析 {len(products)} 个商品")

    except Exception as e:
        print(f"  ❌ 抓取第 {page_num} 页失败: {e}")

    return products


async def scrape_category(browser: Browser, url: str) -> List[Dict]:
    """
    抓取整个分类（多页）
    """
    print(f"\n{'='*60}")
    print(f"🚀 开始抓取分类: {url}")
    print(f"{'='*60}")

    # 创建新页面
    page = await browser.new_page(user_agent=USER_AGENT)

    all_products = []
    current_url = url

    try:
        for page_num in range(1, MAX_PAGES + 1):
            # 抓取当前页
            products = await scrape_page(page, current_url, page_num)
            all_products.extend(products)

            # 检查是否有下一页
            next_button = page.locator("button[title='Next']").or_(
                page.locator(".pagination .next:not(.disabled)")
            ).or_(
                page.locator("a[title='Next']")
            )

            has_next = await next_button.count() > 0
            is_enabled = False

            if has_next:
                try:
                    is_enabled = await next_button.first.is_enabled()
                except Exception:
                    is_enabled = False

            # 如果没有下一页或已达到最大页数，停止翻页
            if not has_next or not is_enabled or page_num >= MAX_PAGES:
                if page_num >= MAX_PAGES:
                    print(f"\n⏹️  已达到最大页数限制 ({MAX_PAGES})")
                else:
                    print(f"\n✅ 已到达最后一页")
                break

            # 点击下一页
            print(f"\n➡️  准备翻到第 {page_num + 1} 页...")
            await next_button.first.click()

            # 随机等待，防止被反爬
            wait_time = random.uniform(MIN_WAIT, MAX_WAIT)
            print(f"⏱️  等待 {wait_time:.1f} 秒...")
            await asyncio.sleep(wait_time)

            # 获取新的 URL
            current_url = page.url

    except Exception as e:
        print(f"❌ 抓取分类失败: {e}")

    finally:
        await page.close()

    print(f"\n📊 分类抓取完成，共获取 {len(all_products)} 个商品")
    return all_products


async def main():
    """
    主函数
    """
    print(f"""
╔══════════════════════════════════════════════════════════╗
║         Newegg 商品爬虫 - Playwright 版                  ║
╚══════════════════════════════════════════════════════════╝
    """)

    print(f"📋 配置:")
    print(f"  - 目标 URL 数量: {len(TARGET_URLS)}")
    print(f"  - 最大页数限制: {MAX_PAGES}")
    print(f"  - 随机等待: {MIN_WAIT}-{MAX_WAIT} 秒")

    all_data = []

    async with async_playwright() as p:
        # 启动浏览器（无头模式）
        browser = await p.chromium.launch(headless=True)

        try:
            # 遍历所有目标 URL
            for idx, url in enumerate(TARGET_URLS, 1):
                print(f"\n\n{'#'*60}")
                print(f"# 处理第 {idx}/{len(TARGET_URLS)} 个分类")
                print(f"{'#'*60}")

                products = await scrape_category(browser, url)
                all_data.extend(products)

        finally:
            await browser.close()

    # 保存数据为 JSON
    if all_data:
        filename = f"newegg_data.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)

        print(f"\n\n{'='*60}")
        print(f"🎉 抓取完成！")
        print(f"  - 总商品数: {len(all_data)}")
        print(f"  - 保存文件: {filename}")
        print(f"{'='*60}")
    else:
        print("\n⚠️  未获取到任何数据")


if __name__ == "__main__":
    asyncio.run(main())
