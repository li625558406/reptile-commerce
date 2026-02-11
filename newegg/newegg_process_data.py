"""
Newegg 通用数据清洗脚本
自动识别产品类型并提取规格参数，导入 PostgreSQL
"""

import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor


class NeweggDataProcessor:
    """Newegg 通用数据处理器"""

    def __init__(self, input_file="newegg_data.json", db_config=None):
        """
        初始化处理器

        Args:
            input_file: 输入JSON文件路径
            db_config: 数据库配置
        """
        self.input_file = Path(input_file)
        self.db_config = db_config or {
            'host': '192.168.2.7',
            'port': 5432,
            'database': 'reptile_db',
            'user': 'konus',
            'password': 'LGligang12345',
            'connect_timeout': 10
        }
        self.raw_data = []
        self.processed_data = []
        self.discarded_count = 0

        # 产品类型识别关键词（注意：优先级高的放在前面）
        self.category_keywords = {
            'Laptop': ['Laptop', 'Notebook', '2-in-1', 'Chromebook', 'Gaming Laptop', 'TouchScreen Laptop'],
            'Gaming PC': ['Gaming PC', 'Desktop PC', 'Pre-Built', 'Gaming Desktop'],
            'CPU': ['Processor', 'CPU'],
            'Motherboard': ['Motherboard', 'LGA', 'Socket AM5', 'ATX', 'mATX', 'ITX'],
            'Memory': ['RAM', 'DDR5', 'DDR4', 'Memory', 'GB (2 x'],
            'SSD': ['SSD', 'Solid State Drive', 'NVMe', 'M.2', 'PCIe Gen'],
            'Graphics Card': ['Graphics Card', 'GPU', 'RTX', 'Radeon', 'GeForce'],
            'Storage': ['Hard Drive', 'HDD'],
            'Power Supply': ['Power Supply', 'PSU', 'W Power Supply'],
            'Case': ['Case', 'Chassis'],
            'Cooler': ['Cooler', 'Heatsink', 'Liquid Cooler', 'AIO'],
            'Camera': ['Camera', 'Webcam', 'Surveillance', 'Security Camera', 'PTZ', 'NVR Kit', 'Dome Camera'],
            'Smart Home': ['Smart Plug', 'Smart Light', 'Hub', 'Sensor', 'Doorbell', 'Thermostat'],
            'Networking': ['Router', 'Switch', 'Access Point', 'WiFi', 'Ethernet'],
            'Other': []
        }

    def load_data(self):
        """加载原始 JSON 数据"""
        if not self.input_file.exists():
            raise FileNotFoundError(f"找不到文件: {self.input_file}")

        with open(self.input_file, 'r', encoding='utf-8') as f:
            self.raw_data = json.load(f)

        print(f"已加载 {len(self.raw_data)} 条原始数据")

    def detect_category(self, title):
        """
        根据标题自动识别产品类别

        Args:
            title: 产品标题

        Returns:
            产品类别
        """
        title_lower = title.lower()

        for category, keywords in self.category_keywords.items():
            for keyword in keywords:
                if keyword.lower() in title_lower:
                    return category

        return 'Other'

    def parse_cpu_specs(self, title):
        """解析 CPU 规格"""
        result = {
            'brand': None, 'series': None, 'model': None,
            'cores': None, 'speed': None, 'socket': None, 'power': None
        }

        # Brand
        brand_match = re.search(r'\b(AMD|Intel)\b', title, re.IGNORECASE)
        if brand_match:
            result['brand'] = brand_match.group(1)

        # Series
        series_patterns = [
            r'\b(Ryzen\s*[3579]|Ryzen\s+Threadripper|EPYC)\b',
            r'\b(Core\s*[ijU][3579]|Core\s+Ultra)\b',
            r'\b(Pentium|Celeron)\b'
        ]
        for pattern in series_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                result['series'] = match.group(1).strip()
                break

        # Model
        model_match = re.search(r'\b(\d{4,5}[A-Za-z]{0,4}[LXK]?)\b', title)
        if model_match:
            result['model'] = model_match.group(1)

        # Cores
        cores_match = re.search(r'(\d+)[\s-]*Co(?:re|res)', title, re.IGNORECASE)
        if cores_match:
            result['cores'] = int(cores_match.group(1))

        # Speed
        speed_match = re.search(r'(\d+\.?\d*)\s*GHz', title, re.IGNORECASE)
        if speed_match:
            result['speed'] = f"{speed_match.group(1)} GHz"

        # Socket
        socket_patterns = [r'Socket\s+([A-Z0-9]+)', r'LGA\s*(\d{4,5})', r'\b(AM[45])\b']
        for pattern in socket_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                socket_val = match.group(1).strip()
                if not socket_val.startswith('LGA') and not socket_val.startswith('AM'):
                    socket_val = f"Socket {socket_val}"
                result['socket'] = socket_val
                break

        # Power
        power_match = re.search(r'(\d{2,3})\s*W(?:\s|,|$|\.|\))', title, re.IGNORECASE)
        if power_match:
            power_val = int(power_match.group(1))
            if 35 <= power_val <= 350:
                result['power'] = f"{power_val}W"

        return result

    def parse_motherboard_specs(self, title):
        """解析主板规格"""
        result = {
            'brand': None, 'chipset': None, 'socket': None,
            'form_factor': None, 'memory_type': None
        }

        # Brand
        brands = ['ASUS', 'GIGABYTE', 'MSI', 'ASRock', 'MSI']
        for brand in brands:
            if brand.lower() in title.lower():
                result['brand'] = brand
                break

        # Chipset
        chipset_match = re.search(r'([ABCXYZ]\d{3,4}|[BZ]\d{3,})', title)
        if chipset_match:
            result['chipset'] = chipset_match.group(1)

        # Socket
        socket_match = re.search(r'Socket\s+([A-Z0-9]+)|LGA\s*(\d{4,5})|AM[45]', title, re.IGNORECASE)
        if socket_match:
            result['socket'] = socket_match.group(0)

        # Form Factor
        if 'ATX' in title:
            result['form_factor'] = 'ATX'
        elif 'mATX' in title or 'Micro ATX' in title:
            result['form_factor'] = 'mATX'
        elif 'ITX' in title:
            result['form_factor'] = 'ITX'

        # Memory Type
        if 'DDR5' in title:
            result['memory_type'] = 'DDR5'
        elif 'DDR4' in title:
            result['memory_type'] = 'DDR4'

        return result

    def parse_memory_specs(self, title):
        """解析内存规格"""
        result = {
            'brand': None, 'capacity_gb': None, 'type': None, 'speed_mhz': None
        }

        # Brand
        brands = ['CORSAIR', 'G.SKILL', 'Kingston', 'Crucial', 'Patriot']
        for brand in brands:
            if brand.lower() in title.lower():
                result['brand'] = brand
                break

        # Capacity
        capacity_match = re.search(r'(\d+)\s*GB', title)
        if capacity_match:
            result['capacity_gb'] = int(capacity_match.group(1))

        # Type
        if 'DDR5' in title:
            result['type'] = 'DDR5'
        elif 'DDR4' in title:
            result['type'] = 'DDR4'

        # Speed
        speed_match = re.search(r'(\d{4})\s*(?:MHz|PC5)', title)
        if speed_match:
            result['speed_mhz'] = int(speed_match.group(1))

        return result

    def parse_ssd_specs(self, title):
        """解析 SSD 规格"""
        result = {
            'brand': None, 'capacity_gb': None, 'interface': None,
            'read_speed': None, 'form_factor': None
        }

        # Brand
        brands = ['SAMSUNG', 'Western Digital', 'WD', 'Crucial', 'Patriot', 'Kingston', 'Sabrent', 'Solidigm']
        for brand in brands:
            if brand.lower() in title.lower():
                result['brand'] = brand
                break

        # Capacity - 改进正则表达式以更准确地匹配
        # 先尝试匹配 TB 格式（带小数点的，如 7.68TB, 3.84TB）
        capacity_match = re.search(r'(\d+\.?\d*)\s*TB', title)
        if capacity_match:
            tb_value = float(capacity_match.group(1))
            result['capacity_gb'] = int(tb_value * 1024)
        else:
            # 匹配 GB 格式，排除包含 TB 的情况（避免 7.68TB 被误匹配为 68GB）
            capacity_match = re.search(r'(\d+)\s*GB(?!\s*\w)', title)
            if capacity_match:
                result['capacity_gb'] = int(capacity_match.group(1))

        # Interface
        if 'PCIe Gen4' in title or 'PCIe 4.0' in title:
            result['interface'] = 'PCIe Gen4'
        elif 'PCIe Gen3' in title or 'PCIe 3.0' in title:
            result['interface'] = 'PCIe Gen3'

        # Read Speed
        read_match = re.search(r'(\d+,?\d*)\s*MB/s', title)
        if read_match:
            result['read_speed'] = read_match.group(1)

        # Form Factor
        if 'M.2' in title:
            result['form_factor'] = 'M.2'
        elif '2.5"' in title:
            result['form_factor'] = '2.5 inch'

        return result

    def parse_laptop_specs(self, title):
        """解析笔记本规格"""
        result = {
            'brand': None, 'cpu': None, 'ram': None,
            'storage': None, 'screen_size': None, 'gpu': None
        }

        # Brand
        brands = ['ASUS', 'MSI', 'Acer', 'Lenovo', 'Dell', 'HP', 'Razer', 'GIGABYTE', 'XIDAX']
        for brand in brands:
            if brand.lower() in title.lower():
                result['brand'] = brand
                break

        # CPU
        cpu_patterns = [
            r'(Intel Core [iU3579][-\s]*\d+[A-Za-z]{0,4})',
            r'(Intel Core Ultra [3579]\s*\d+[A-Za-z]{0,4})',
            r'(AMD Ryzen [3579]\s*\d{4}[A-Za-z]{0,4})',
            r'(Intel Core \d+ Proces)',
        ]
        for pattern in cpu_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                result['cpu'] = match.group(1).strip()
                break

        # RAM
        ram_match = re.search(r'(\d+)\s*GB\s*DDR[45]', title, re.IGNORECASE)
        if ram_match:
            result['ram'] = f"{ram_match.group(1)} GB"

        # Storage
        storage_match = re.search(r'(\d+)\s*GB\s*(SSD|NVMe|M\.2)', title, re.IGNORECASE)
        if storage_match:
            result['storage'] = f"{storage_match.group(1)} GB {storage_match.group(2)}"
        else:
            storage_match = re.search(r'(\d+)\s*TB\s*SSD', title, re.IGNORECASE)
            if storage_match:
                result['storage'] = f"{storage_match.group(1)} TB SSD"

        # Screen Size
        screen_match = re.search(r'(\d+\.?\d*)["\s]', title)
        if screen_match and float(screen_match.group(1)) >= 10 and float(screen_match.group(1)) <= 20:
            result['screen_size'] = f"{screen_match.group(1)} inch"

        # GPU
        gpu_patterns = [
            r'(RTX\s*\d+[A-Za-z]{0,4}\s*Laptop)',
            r'(GeForce\s*RTX\s*\d+[A-Za-z]{0,4}\s*Laptop)',
            r'(Radeon\s*RX\s*\d+[A-Za-z]{0,4})',
        ]
        for pattern in gpu_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                result['gpu'] = match.group(1).strip()
                break

        return result

    def parse_gaming_pc_specs(self, title):
        """解析整机规格"""
        result = {
            'brand': None, 'cpu': None, 'gpu': None,
            'ram': None, 'storage': None
        }

        # Brand
        brands = ['ABS', 'iBUYPOWER', 'CYBERPOWERPC', 'Skytech', 'CLX', 'Xidax']
        for brand in brands:
            if brand.lower() in title.lower():
                result['brand'] = brand
                break

        # CPU
        cpu_patterns = [
            r'(Intel Core [iU3579][-\s]*\d+[A-Za-z]{0,4})',
            r'(Intel Core Ultra [3579]\s*\d+[A-Za-z]{0,4})',
            r'(AMD Ryzen [3579]\s*\d{4}[A-Za-z]{0,4})',
        ]
        for pattern in cpu_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                result['cpu'] = match.group(1).strip()
                break

        # GPU
        gpu_patterns = [
            r'(RTX\s*\d+[A-Za-z]{0,4})',
            r'(GeForce\s*RTX\s*\d+[A-Za-z]{0,4})',
            r'(GeForce\s*GTX\s*\d+[A-Za-z]{0,4})',
            r'(Radeon\s*RX\s*\d+[A-Za-z]{0,4})',
        ]
        for pattern in gpu_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                result['gpu'] = match.group(1).strip()
                break

        # RAM
        ram_match = re.search(r'(\d+)\s*GB\s*DDR[45]', title, re.IGNORECASE)
        if ram_match:
            result['ram'] = f"{ram_match.group(1)} GB"

        # Storage
        storage_match = re.search(r'(\d+)\s*(GB|TB)\s*SSD|NVMe', title, re.IGNORECASE)
        if storage_match:
            result['storage'] = f"{storage_match.group(1)} {storage_match.group(2)} SSD"

        return result

    def extract_price(self, price_str):
        """从价格字符串中提取数字"""
        if not price_str or price_str == '0':
            return None

        numbers = re.findall(r'[\d,]+\.?\d*', str(price_str))
        if numbers:
            price = float(numbers[0].replace(',', ''))
            return price if price > 0 else None
        return None

    def generate_amazon_link(self, title, category):
        """
        生成 Amazon 搜索链接

        Args:
            title: 产品标题
            category: 产品类别

        Returns:
            Amazon 搜索 URL
        """
        # 简化标题用于搜索
        search_terms = []

        # 提取品牌
        brands = ['AMD', 'Intel', 'ASUS', 'GIGABYTE', 'MSI', 'ASRock',
                  'CORSAIR', 'SAMSUNG', 'eufy', 'Arlo', 'Ubiquiti',
                  'Reolink', 'Kasa', 'Philips', 'Eve']
        for brand in brands:
            if brand.lower() in title.lower():
                search_terms.append(brand)
                break

        # 提取关键词
        if category == 'CPU':
            model_match = re.search(r'\d{4,5}[A-Za-z]{0,4}', title)
            if model_match:
                search_terms.append(model_match.group())
        else:
            # 对于其他类别，使用标题前几个词
            words = title.split()[:5]
            search_terms.extend(words)

        if not search_terms:
            search_terms = title.split()[:3]

        search_term = " ".join(search_terms[:4])  # 限制为4个关键词
        encoded_search = urllib.parse.quote_plus(search_term)

        return f"https://www.amazon.com/s?k={encoded_search}&tag=YOUR_TAG-20"

    def normalize_record(self, record):
        """
        标准化单条记录

        Args:
            record: 原始记录

        Returns:
            标准化后的记录，如果数据无效返回 None
        """
        title = record.get('title', '')
        price = self.extract_price(record.get('price', ''))

        # 过滤: 价格必须大于0
        if not price:
            return None

        # 识别类别
        category = self.detect_category(title)

        normalized = {
            'original_data': record,
            'title': title,
            'category': category,
            'price': price,
            'image_url': record.get('img_url', ''),
            'product_link': record.get('product_link', ''),
            'item_features': record.get('item_features', []),  # 直接保存列表，psycopg2 自动转换为 JSONB
            'processed_at': datetime.now().isoformat()
        }

        # 根据类别解析规格
        if category == 'CPU':
            specs = self.parse_cpu_specs(title)
            normalized['brand'] = specs.get('brand')
            normalized['specs'] = specs  # 直接保存 dict，psycopg2 自动转换为 JSONB
        elif category == 'Motherboard':
            specs = self.parse_motherboard_specs(title)
            normalized['brand'] = specs.get('brand')
            normalized['specs'] = specs
        elif category == 'Memory':
            specs = self.parse_memory_specs(title)
            normalized['brand'] = specs.get('brand')
            normalized['specs'] = specs
        elif category == 'SSD':
            specs = self.parse_ssd_specs(title)
            normalized['brand'] = specs.get('brand')
            normalized['specs'] = specs
        elif category == 'Laptop':
            # 笔记本特殊处理 - 提取基本规格
            specs = self.parse_laptop_specs(title)
            normalized['brand'] = specs.get('brand')
            normalized['specs'] = specs
        elif category == 'Gaming PC':
            # 整机特殊处理 - 提取基本规格
            specs = self.parse_gaming_pc_specs(title)
            normalized['brand'] = specs.get('brand')
            normalized['specs'] = specs
        else:
            # 其他类别，只保存基本信息
            normalized['brand'] = None
            normalized['specs'] = {}

        # 生成 Amazon 链接
        normalized['amazon_link'] = self.generate_amazon_link(title, category)

        return normalized

    def process_all(self):
        """处理所有数据"""
        print("=" * 60)
        print("开始 Newegg 数据清洗...")
        print("=" * 60)

        valid_records = []
        category_count = {}

        for idx, record in enumerate(self.raw_data, 1):
            normalized = self.normalize_record(record)

            if normalized:
                valid_records.append(normalized)
                category = normalized['category']
                category_count[category] = category_count.get(category, 0) + 1

                brand = normalized.get('brand') or 'Unknown'
                title_short = normalized['title'][:40]
                print(f"[{idx}/{len(self.raw_data)}] [OK] [{category}] {brand} - {title_short}...")
            else:
                self.discarded_count += 1
                title_short = record.get('title', '')[:40]
                print(f"[{idx}/{len(self.raw_data)}] [X] 已丢弃: {title_short}...")

        self.processed_data = valid_records

        print("=" * 60)
        print(f"数据处理完成!")
        print(f"  有效记录: {len(self.processed_data)}")
        print(f"  丢弃记录: {self.discarded_count}")
        print(f"\n类别分布:")
        for cat, count in sorted(category_count.items()):
            print(f"  {cat}: {count}")

    def save_to_json(self, output_file= "newegg_processed.json"):
        """保存处理后的数据到 JSON"""
        output_path = Path(output_file)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.processed_data, f, ensure_ascii=False, indent=2)

        print(f"\n已保存处理后的数据到: {output_path.absolute()}")

    def connect_db(self):
        """连接 PostgreSQL 数据库"""
        try:
            conn = psycopg2.connect(**self.db_config)
            return conn
        except Exception as e:
            print(f"数据库连接失败: {e}")
            raise

    def create_table_if_not_exists(self, conn):
        """创建数据表（如果不存在）"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS newegg_products (
            id SERIAL PRIMARY KEY,
            title VARCHAR(1000),
            category VARCHAR(50),
            brand VARCHAR(100),
            price DECIMAL(10, 2),
            image_url TEXT,
            product_link TEXT,
            amazon_link TEXT,
            item_features JSONB,
            specs JSONB,
            processed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 创建索引
        CREATE INDEX IF NOT EXISTS idx_newegg_category ON newegg_products(category);
        CREATE INDEX IF NOT EXISTS idx_newegg_brand ON newegg_products(brand);
        CREATE INDEX IF NOT EXISTS idx_newegg_price ON newegg_products(price);

        -- 添加注释
        COMMENT ON TABLE newegg_products IS 'Newegg 产品数据';
        COMMENT ON COLUMN newegg_products.category IS '产品类别 (CPU, Motherboard, Memory, SSD, Camera, etc.)';
        COMMENT ON COLUMN newegg_products.specs IS '产品规格参数 (JSONB)';
        """

        try:
            with conn.cursor() as cur:
                cur.execute(create_table_sql)
                conn.commit()
                print("数据表检查完成")
        except Exception as e:
            print(f"创建表失败: {e}")
            conn.rollback()
            raise

    def insert_data(self, conn):
        """插入数据到数据库"""
        insert_sql = """
        INSERT INTO newegg_products (
            title, category, brand, price, image_url, product_link,
            amazon_link, item_features, specs, processed_at
        ) VALUES (
            %(title)s, %(category)s, %(brand)s, %(price)s, %(image_url)s, %(product_link)s,
            %(amazon_link)s, %(item_features)s, %(specs)s, %(processed_at)s
        )
        ON CONFLICT (title) DO UPDATE SET
            category = EXCLUDED.category,
            brand = EXCLUDED.brand,
            price = EXCLUDED.price,
            amazon_link = EXCLUDED.amazon_link,
            specs = EXCLUDED.specs,
            updated_at = CURRENT_TIMESTAMP
        """

        try:
            with conn.cursor() as cur:
                # 添加唯一约束（如果不存在）
                try:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = 'unique_newegg_title'
                        )
                    """)
                    constraint_exists = cur.fetchone()[0]

                    if not constraint_exists:
                        cur.execute("""
                            ALTER TABLE newegg_products
                            ADD CONSTRAINT unique_newegg_title
                            UNIQUE (title)
                        """)
                        print("已添加唯一约束: unique_newegg_title")
                except Exception as e:
                    print(f"添加约束警告: {e}")

                # 批量插入，转换 dict/list 为 JSON 字符串给 psycopg2
                for record in self.processed_data:
                    # 准备数据库记录（转换 dict/list 为 JSON 字符串）
                    db_record = record.copy()

                    # 将 specs dict 转换为 JSON 字符串
                    if isinstance(db_record.get('specs'), dict):
                        db_record['specs'] = json.dumps(db_record['specs'], ensure_ascii=False)
                    elif db_record.get('specs') is None:
                        db_record['specs'] = json.dumps({}, ensure_ascii=False)

                    # 将 item_features list 转换为 JSON 字符串
                    if isinstance(db_record.get('item_features'), list):
                        db_record['item_features'] = json.dumps(db_record['item_features'], ensure_ascii=False)
                    elif db_record.get('item_features') is None:
                        db_record['item_features'] = json.dumps([], ensure_ascii=False)

                    cur.execute(insert_sql, db_record)

                conn.commit()
                print(f"成功插入 {len(self.processed_data)} 条记录到数据库")
        except Exception as e:
            print(f"插入数据失败: {e}")
            conn.rollback()
            raise

    def save_to_database(self):
        """保存数据到 PostgreSQL"""
        print("\n" + "=" * 60)
        print("开始连接数据库...")

        conn = self.connect_db()
        print(f"数据库连接成功: {self.db_config['host']}:{self.db_config['port']}/{self.db_config['database']}")

        try:
            self.create_table_if_not_exists(conn)
            self.insert_data(conn)

            # 查询统计
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) as total FROM newegg_products")
                total = cur.fetchone()['total']
                print(f"\n数据库中共有 {total} 条记录")

                # 按类别统计
                cur.execute("SELECT category, COUNT(*) as count FROM newegg_products GROUP BY category ORDER BY count DESC")
                categories = cur.fetchall()
                print("\n数据库中类别分布:")
                for c in categories:
                    print(f"  {c['category']}: {c['count']} 条")

        finally:
            conn.close()
            print("数据库连接已关闭")

    def print_summary(self):
        """打印数据摘要"""
        if not self.processed_data:
            return

        print("\n" + "=" * 60)
        print("数据摘要")
        print("=" * 60)

        # 按类别统计
        categories = {}
        brands = {}
        for r in self.processed_data:
            cat = r['category']
            categories[cat] = categories.get(cat, 0) + 1

            brand = r.get('brand')
            if brand:
                brands[brand] = brands.get(brand, 0) + 1

        print(f"\n类别统计 (Top 5):")
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {cat}: {count}")

        print(f"\n品牌统计 (Top 5):")
        for brand, count in sorted(brands.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {brand}: {count}")

        # 价格范围
        prices = [r['price'] for r in self.processed_data if r['price']]
        if prices:
            print(f"\n价格范围:")
            print(f"  最低: ${min(prices):.2f}")
            print(f"  最高: ${max(prices):.2f}")
            print(f"  平均: ${sum(prices)/len(prices):.2f}")


def main():
    """主函数"""
    db_config = {
        'host': '192.168.2.7',
        'port': 5432,
        'database': 'reptile_db',
        'user': 'konus',
        'password': 'LGligang12345',
        'connect_timeout': 10
    }

    processor = NeweggDataProcessor(
        input_file="newegg_data.json",
        db_config=db_config
    )

    try:
        # 1. 加载数据
        processor.load_data()

        # 2. 数据清洗
        processor.process_all()

        # 3. 保存到 JSON
        processor.save_to_json("newegg_processed.json")

        # 4. 保存到数据库
        processor.save_to_database()

        # 5. 打印摘要
        processor.print_summary()

        print("\n处理完成!")

    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("请确保 newegg_data.json 文件存在于当前目录")
    except Exception as e:
        print(f"\n处理过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
