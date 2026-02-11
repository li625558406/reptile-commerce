"""
Sylvane Air Purifiers Scraper
爬取 Sylvane 网站的空气净化器产品数据和规格信息
使用 Playwright + playwright-stealth 抗反爬
"""

import asyncio
import json
import random
import re
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser, BrowserContext


class SylvaneScraper:
    """Sylvane 空气净化器爬虫"""

    BASE_URL = "https://www.sylvane.com"
    START_URL = f"{BASE_URL}/collections/air-purifiers"
    MAX_PAGES = 3  # 测试限制页数
    OUTPUT_FILE = "sylvane_raw.json"

    def __init__(self, headless: bool = True, max_pages: int = MAX_PAGES):
        """
        初始化爬虫

        Args:
            headless: 是否使用无头模式
            max_pages: 最大爬取页数
        """
        self.headless = headless
        self.max_pages = max_pages
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.products_data: List[Dict] = []

    async def apply_stealth(self):
        """应用反检测脚本"""
        stealth_script = """
        () => {
            // 覆盖 navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // 覆盖 navigator.plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // 覆盖 navigator.languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });

            // 添加 chrome 对象
            window.chrome = {
                runtime: {}
            };

            // 覆盖 permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // 覆盖 playwright 检测
            Object.defineProperty(navigator, 'automation', {
                get: () => false
            });
        }
        """
        await self.page.evaluate(stealth_script)

    async def init(self):
        """初始化浏览器"""
        self.playwright = await async_playwright().start()

        # 启动浏览器
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ]
        )

        # 创建浏览器上下文
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            locale='en-US',
        )

        # 创建页面
        self.page = await self.context.new_page()

        # 应用自定义 stealth 脚本
        await self.apply_stealth()

        print(f"浏览器初始化完成 (headless={self.headless})")

    async def close(self):
        """关闭浏览器"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
        print("浏览器已关闭")

    async def random_delay(self, min_sec: float = 2.0, max_sec: float = 5.0):
        """随机延迟"""
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)
        return delay

    async def get_product_links_from_page(self) -> List[str]:
        """
        从当前列表页获取所有商品链接

        Returns:
            商品详情页URL列表
        """
        product_links = []

        try:
            # 等待页面加载后查找商品链接
            await asyncio.sleep(2)

            # 查找所有商品链接 - 使用更多可能的选择器
            products = await self.page.query_selector_all('a[href*="/products/"]')

            if not products:
                # 尝试其他选择器
                products = await self.page.query_selector_all('.product-item a, .product-card a, .product a')

            for product in products:
                try:
                    href = await product.get_attribute('href')
                    if href and '/products/' in href:
                        # 构建完整URL
                        full_url = href if href.startswith('http') else self.BASE_URL + href
                        if full_url not in product_links:
                            product_links.append(full_url)
                except:
                    continue

            print(f"  从当前页找到 {len(product_links)} 个商品链接")
            return product_links

        except Exception as e:
            print(f"  获取商品链接失败: {e}")
            return []

    async def has_next_page(self) -> bool:
        """检查是否有下一页"""
        try:
            # 查找 "Next" 按钮或分页链接
            next_button = await self.page.query_selector('a[rel="next"], .pagination__next, .next, [aria-label="Next"]')
            if next_button:
                # 检查按钮是否可点击
                is_disabled = await next_button.get_attribute('disabled')
                class_list = await next_button.get_attribute('class') or ''
                return is_disabled is None and 'disabled' not in class_list.lower()
            return False
        except:
            return False

    async def go_to_next_page(self) -> bool:
        """跳转到下一页"""
        try:
            # 查找并点击 "Next" 按钮
            next_button = await self.page.query_selector('a[rel="next"], .pagination__next, .next, [aria-label="Next"]')

            if next_button:
                await next_button.click()
                await asyncio.sleep(3)  # 等待页面加载
                return True
            return False
        except Exception as e:
            print(f"  翻页失败: {e}")
            return False

    async def extract_text_by_label(self, selectors: List[str]) -> Optional[str]:
        """
        根据多个可能的selector选择器提取文本

        Args:
            selectors: 选择器列表

        Returns:
            提取的文本，失败返回None
        """
        for selector in selectors:
            try:
                elem = await self.page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    return text.strip()
            except:
                continue
        return None

    async def find_spec_value(self, spec_name: str) -> Optional[str]:
        """
        在规格区域中查找特定规格的值

        Args:
            spec_name: 规格名称（如 "Coverage Area", "CADR Smoke"）

        Returns:
            规格值
        """
        # 多种可能的规格选择器模式
        patterns = [
            # 模式1: 表格形式 (label - value)
            f'//tr[contains(., "{spec_name}")]//td[last()]',
            f'//dt[contains(., "{spec_name}")]/following-sibling::dd[1]',
            # 模式2: 列表形式
            f'//li[contains(., "{spec_name}")]',
            # 模式3: div形式
            f'//div[contains(@class, "spec") and contains(., "{spec_name}")]',
        ]

        for pattern in patterns:
            try:
                elem = await self.page.query_selector(f'xpath={pattern}')
                if elem:
                    text = await elem.inner_text()
                    # 移除标签名，只保留值
                    text = text.replace(spec_name, '').strip(': \n\t')
                    return text if text else None
            except:
                continue

        return None

    async def scrape_product_detail(self, product_url: str) -> Optional[Dict]:
        """
        抓取单个商品的详情页

        Args:
            product_url: 商品详情页URL

        Returns:
            商品信息字典
        """
        product_data = {
            'url': product_url,
            'scraped_at': datetime.now().isoformat()
        }

        try:
            print(f"    正在抓取: {product_url}")

            # 导航到详情页 - 增加超时时间
            await self.page.goto(product_url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(3)  # 等待动态内容加载

            # 等待主要内容加载
            try:
                await self.page.wait_for_selector('body', timeout=5000)
            except:
                pass  # 继续尝试

            # 1. 提取商品标题
            name_selectors = [
                'h1.product-title',
                'h1.product__title',
                'h1[class*="title"]',
                'h1',
                '.product-name',
                '[data-product-title]'
            ]
            product_data['product_name'] = await self.extract_text_by_label(name_selectors) or "N/A"

            # 2. 提取价格
            price_selectors = [
                '.product-price',
                '.price',
                '[data-product-price]',
                '.current-price',
                '.sales-price',
                'span.money'
            ]
            price_text = await self.extract_text_by_label(price_selectors)
            product_data['price'] = price_text or "N/A"

            # 3. 提取主图
            image_selectors = [
                '.product-image img',
                '.product-gallery img',
                'img[class*="product"]',
                '.featured-image img',
                '[data-product-image]'
            ]
            img_elem = await self.page.query_selector(image_selectors[0])
            if img_elem:
                product_data['image_url'] = await img_elem.get_attribute('src') or ""
            else:
                product_data['image_url'] = ""

            # 4. 查找并点击 Specifications 标签/区域
            spec_tab_selectors = [
                'a:has-text("Specifications")',
                'button:has-text("Specifications")',
                '[data-tab="Specifications"]',
                '.tab-specifications',
                '#specifications-tab'
            ]

            spec_clicked = False
            for selector in spec_tab_selectors:
                try:
                    tab = await self.page.query_selector(selector)
                    if tab:
                        await tab.click()
                        await asyncio.sleep(1)
                        spec_clicked = True
                        print("      已点击 Specifications 标签")
                        break
                except:
                    continue

            if not spec_clicked:
                # 可能规格就在页面上，不需要点击
                print("      未找到规格标签，尝试直接提取")

            # 5. 提取各项规格
            specs_to_extract = [
                ('coverage_area', ['Coverage Area', 'Room Size', 'Coverage', 'Area Coverage']),
                ('cadr_smoke', ['CADR Smoke', 'Smoke CADR', 'CADR - Smoke']),
                ('cadr_pollen', ['CADR Pollen', 'Pollen CADR', 'CADR - Pollen']),
                ('cadr_dust', ['CADR Dust', 'Dust CADR', 'CADR - Dust']),
                ('noise_level', ['Noise Level', 'Sound Level', 'Decibels', 'dB', 'Noise']),
                ('filter_type', ['Filter Type', 'Filter', 'Filtration', 'Technology']),
                ('fan_speeds', ['Fan Speeds', 'Speeds', 'Fan Settings', 'Speed Settings']),
            ]

            for field_name, possible_labels in specs_to_extract:
                value = None
                for label in possible_labels:
                    found = await self.find_spec_value(label)
                    if found:
                        value = found
                        break
                product_data[field_name] = value or "N/A"

            print(f"      ✓ 抓取成功: {product_data['product_name'][:50]}...")
            return product_data

        except Exception as e:
            print(f"      ✗ 抓取失败: {e}")
            product_data['error'] = str(e)
            return product_data

    async def scrape_all_pages(self):
        """爬取所有列表页和商品详情"""
        all_links = []
        page_num = 1

        print("=" * 60)
        print(f"开始爬取 Sylvane 空气净化器数据")
        print(f"起始 URL: {self.START_URL}")
        print(f"最大页数: {self.max_pages}")
        print("=" * 60)

        # 访问起始页 - 使用 domcontentloaded 而不是 networkidle
        await self.page.goto(self.START_URL, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(5)  # 等待页面完全加载

        # 遍历列表页
        while page_num <= self.max_pages:
            print(f"\n[第 {page_num} 页]")

            # 获取当前页的所有商品链接
            product_links = await self.get_product_links_from_page()
            all_links.extend(product_links)

            # 检查是否有下一页
            if page_num < self.max_pages and await self.has_next_page():
                print(f"  准备跳转到第 {page_num + 1} 页...")
                if await self.go_to_next_page():
                    page_num += 1
                    await asyncio.sleep(2)
                else:
                    print("  无法跳转到下一页，结束")
                    break
            else:
                print(f"  已达到最大页数限制 ({self.max_pages}) 或没有更多页面")
                break

        print(f"\n共找到 {len(all_links)} 个商品链接")
        print("=" * 60)

        # 去重
        unique_links = list(dict.fromkeys(all_links))
        print(f"去重后: {len(unique_links)} 个商品")

        # 遍历所有商品链接，抓取详情
        print(f"\n开始抓取商品详情...")
        print("=" * 60)

        for idx, product_url in enumerate(unique_links, 1):
            print(f"\n[{idx}/{len(unique_links)}]")

            # 随机延迟
            await self.random_delay(2, 5)

            # 抓取商品详情
            product_data = await self.scrape_product_detail(product_url)
            if product_data:
                self.products_data.append(product_data)

        print("=" * 60)
        print(f"爬取完成! 共成功抓取 {len(self.products_data)} 个商品")

    def save_results(self):
        """保存结果到JSON文件"""
        output_path = Path(self.OUTPUT_FILE)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.products_data, f, ensure_ascii=False, indent=2)

        print(f"\n数据已保存到: {output_path.absolute()}")
        print(f"文件大小: {output_path.stat().st_size / 1024:.2f} KB")

        # 打印统计信息
        print("\n=== 数据统计 ===")
        for field in ['product_name', 'price', 'coverage_area', 'cadr_smoke', 'filter_type']:
            count = sum(1 for p in self.products_data if p.get(field) and p[field] != 'N/A')
            print(f"  {field}: {count}/{len(self.products_data)}")


async def main():
    """主函数"""
    # 创建爬虫实例
    # headless=False 可以看到浏览器运行过程，调试时建议设为 False
    scraper = SylvaneScraper(headless=False, max_pages=3)

    try:
        await scraper.init()
        await scraper.scrape_all_pages()
        scraper.save_results()

        # 显示前3个商品数据
        if scraper.products_data:
            print("\n=== 示例数据（前3个商品）===")
            for i, product in enumerate(scraper.products_data[:3], 1):
                print(f"\n--- 商品 {i} ---")
                for key, value in product.items():
                    if value and value != 'N/A' and key not in ['scraped_at', 'url']:
                        print(f"  {key}: {value}")

    except Exception as e:
        print(f"\n爬取过程发生错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
