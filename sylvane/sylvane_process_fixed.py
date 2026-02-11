"""
Sylvane Air Purifiers 数据清洗脚本
处理 sylvane_raw.json，提取规格参数并导入 PostgreSQL
"""

import re
import json
import urllib.parse
from datetime import datetime
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor


class SylvaneDataProcessor:
    """Sylvane 空气净化器数据处理器"""

    def __init__(self, input_file="sylvane_raw.json", db_config=None):
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

    def load_data(self):
        """加载原始 JSON 数据"""
        if not self.input_file.exists():
            raise FileNotFoundError(f"找不到文件: {self.input_file}")

        with open(self.input_file, 'r', encoding='utf-8') as f:
            self.raw_data = json.load(f)

        print(f"已加载 {len(self.raw_data)} 条原始数据")

    @staticmethod
    def extract_coverage_area(value):
        """从覆盖面积文本中提取数字"""
        if not value or value == 'N/A':
            return None

        # 移除 "sq. ft."、"square feet"、"Whole House" 等单位和文本
        text = value.lower()
        text = re.sub(r'sq\.?\s*ft\.?|square\s+feet|up\s+to|approximately|covers?\s+up\s+to|whole\s+house|manufacturer-suggested', '', text)
        text = text.strip()

        # 提取所有数字（限制在合理范围内：10-5000 sq. ft.）
        numbers = re.findall(r'[\d,]+', text)

        # 取最大的有效数字（通常是总面积）
        if numbers:
            cleaned_numbers = [int(n.replace(',', '').strip()) for n in numbers if n.replace(',', '').strip()]
            # 过滤掉异常值，保留合理的空气净化器覆盖面积
            valid_numbers = [n for n in cleaned_numbers if 50 <= n <= 3000]
            if valid_numbers:
                max_num = max(valid_numbers)
                return max_num if max_num > 0 else None
        return None

    @staticmethod
    def extract_cadr_smoke(value):
        """从文本中提取烟雾 CADR 值"""
        if not value or value == 'N/A':
            return None
        return self._extract_single_number(value)

    @staticmethod
    def extract_cadr_pollen(value):
        """从文本中提取花粉 CADR 值"""
        if not value or value == 'N/A':
            return None
        return self._extract_single_number(value)

    @staticmethod
    def extract_cadr_dust(value):
        """从文本中提取灰尘 CADR 值"""
        if not value or value == 'N/A':
            return None
        return self._extract_single_number(value)

    @staticmethod
    def _extract_single_number(value):
        """提取单个数值"""
        if not value:
            return None
        # 提取所有数字
        numbers = re.findall(r'\d+', str(value))
        if numbers:
            # 返回最大的数值
            return max([int(n) for n in numbers])
        return None

    @staticmethod
    def extract_noise_level(value):
        """从噪音文本中提取最低和最高值"""
        if not value or value == 'N/A':
            return {'min_noise': None, 'max_noise': None}

        # 移除 dB、decibel 等单位
        text = value.lower()
        text = re.sub(r'db|decibels?|dba|decibel\s+level|noise\s+level|maximum|minimum', '', text)
        text = text.strip()

        # 提取数字（包括小数）
        # 匹配整数和小数，例如：53.8, 46, 55.1
        numbers = re.findall(r'\d+\.?\d*', text)
        # 过滤空字符串并转换为浮点数
        numbers = [float(n) for n in numbers if n]

        if not numbers:
            return {'min_noise': None, 'max_noise': None}

        if len(numbers) == 1:
            # 只有一个数字，min 和 max 相同
            noise_val = int(numbers[0]) if numbers[0] == int(numbers[0]) else numbers[0]
            return {'min_noise': noise_val, 'max_noise': noise_val}

        # 取最小和最大
        min_val = min(numbers)
        max_val = max(numbers)
        # 如果是整数则转为 int，否则保留浮点数
        min_noise = int(min_val) if min_val == int(min_val) else min_val
        max_noise = int(max_val) if max_val == int(max_val) else max_val

        return {'min_noise': min_noise, 'max_noise': max_noise}

    @staticmethod
    def extract_filter_type(value):
        """提取滤网类型"""
        if not value or value == 'N/A':
            return None
        return value

    @staticmethod
    def extract_fan_speeds(value):
        """提取风扇档位"""
        if not value or value == 'N/A':
            return None

        # 先尝试匹配数字开头的档位描述
        # 匹配 "3", "Three", "Two" 等
        text = str(value).lower().strip()

        # 数字模式：直接提取数字
        number_match = re.search(r'\b(\d+)\b', text)
        if number_match:
            return int(number_match.group(1))

        # 文字模式：匹配英文数字
        word_numbers = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
        }
        for word, num in word_numbers.items():
            if word in text:
                return num

        return None

    @staticmethod
    def extract_price(price_str):
        """从价格字符串中提取数字"""
        if not price_str or price_str == '0' or price_str == 'N/A':
            return None

        # 清理字符串，移除控制字符和换行
        clean_text = price_str.replace('\n', ' ').replace('\r', ' ')
        clean_text = clean_text.replace('Sale price', '').replace('Regular price', '')
        clean_text = clean_text.strip()

        # 提取所有数字（包括小数）
        numbers = re.findall(r'[\d,]+\.?\d*', clean_text)

        if numbers:
            # 取第一个有效的价格数字
            for num in numbers:
                price = float(num.replace(',', ''))
                if price > 0:
                    return price
        return None

    @staticmethod
    def generate_amazon_link(product_name):
        """生成 Amazon 搜索链接"""
        # 简化商品名称，移除通用词
        title = product_name.lower()
        stop_words = ['air purifier', 'air purifiers', 'hepa', 'model', 'series']

        for word in stop_words:
            title = title.replace(word, '')

        # 提取关键词（品牌 + 型号前几个词）
        words = title.split()[:5]

        search_term = " ".join(words)
        encoded_search = urllib.parse.quote_plus(search_term)

        return f"https://www.amazon.com/s?k={encoded_search}&tag=YOUR_TAG-20"

    def normalize_record(self, record):
        """标准化单条记录"""
        product_name = record.get('product_name', '')

        # 提取价格
        price = self.extract_price(record.get('price', ''))
        if not price:
            print(f"  跳过（无价格）: {product_name[:50]}...")
            return None

        normalized = {
            'product_name': product_name,
            'url': record.get('url', ''),
            'price': price,
            'image_url': record.get('image_url', ''),
            'coverage_area': self.extract_coverage_area(record.get('coverage_area')),
            'cadr_smoke': self.extract_cadr_smoke(record.get('cadr_smoke')),
            'cadr_pollen': self.extract_cadr_pollen(record.get('cadr_pollen')),
            'cadr_dust': self.extract_cadr_dust(record.get('cadr_dust')),
            'noise_level': self.extract_noise_level(record.get('noise_level')),
            'filter_type': self.extract_filter_type(record.get('filter_type')),
            'fan_speeds': self.extract_fan_speeds(record.get('fan_speeds')),
            'amazon_link': self.generate_amazon_link(product_name),
            'processed_at': datetime.now().isoformat()
        }

        return normalized

    def process_all(self):
        """处理所有数据"""
        print("=" * 60)
        print("开始 Sylvane 数据清洗...")
        print("=" * 60)

        valid_records = []

        for idx, record in enumerate(self.raw_data, 1):
            normalized = self.normalize_record(record)

            if normalized:
                valid_records.append(normalized)
                name = normalized['product_name'][:40]
                print(f"[{idx}/{len(self.raw_data)}] [OK] {name}")
            else:
                print(f"[{idx}/{len(self.raw_data)}] [X] 跳过: {record.get('product_name', '')[:50]}...")

        self.processed_data = valid_records

        print("=" * 60)
        print(f"数据处理完成!")
        print(f"  有效记录: {len(self.processed_data)}")

    def save_to_json(self, output_file="sylvane_processed.json"):
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
        """创建数据表"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS sylvane_products (
            id SERIAL PRIMARY KEY,
            product_name VARCHAR(500),
            url TEXT,
            price DECIMAL(10, 2),
            image_url TEXT,
            coverage_area INTEGER,
            cadr_smoke INTEGER,
            cadr_pollen INTEGER,
            cadr_dust INTEGER,
            noise_level VARCHAR(50),
            filter_type VARCHAR(200),
            fan_speeds VARCHAR(50),
            amazon_link TEXT,
            processed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        create_index_sql = """
        CREATE INDEX IF NOT EXISTS idx_sylvane_price ON sylvane_products(price);
        CREATE INDEX IF NOT EXISTS idx_sylvane_coverage ON sylvane_products(coverage_area);
        """

        add_constraint_sql = """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'unique_product_name'
            ) THEN
                ALTER TABLE sylvane_products
                ADD CONSTRAINT unique_product_name UNIQUE (product_name);
            END IF;
        END $$;
        """

        comment_sql = """
        COMMENT ON TABLE sylvane_products IS 'Sylvane 空气净化器产品数据';
        """

        try:
            with conn.cursor() as cur:
                # 创建表（如果不存在）
                cur.execute(create_table_sql)

                # 创建索引
                cur.execute(create_index_sql)

                # 添加唯一约束（如果不存在）
                try:
                    cur.execute(add_constraint_sql)
                except Exception as constraint_err:
                    print(f"  注意: 添加唯一约束时出现问题: {constraint_err}")
                    print(f"  如果表中有重复数据，请先清理重复的 product_name")

                # 添加表注释
                try:
                    cur.execute(comment_sql)
                except:
                    pass  # 忽略注释错误

                conn.commit()
                print("数据表检查完成")
        except Exception as e:
            print(f"创建表失败: {e}")
            conn.rollback()
            raise

    def insert_data(self, conn):
        """插入数据到数据库"""
        insert_sql = """
        INSERT INTO sylvane_products (
            product_name, url, price, image_url, coverage_area,
            cadr_smoke, cadr_pollen, cadr_dust, noise_level, filter_type, fan_speeds, amazon_link, processed_at
        ) VALUES (
            %(product_name)s, %(url)s, %(price)s, %(image_url)s, %(coverage_area)s,
            %(cadr_smoke)s, %(cadr_pollen)s, %(cadr_dust)s, %(noise_level)s,
            %(filter_type)s, %(fan_speeds)s, %(amazon_link)s, %(processed_at)s
        )
        ON CONFLICT (product_name) DO UPDATE SET
            price = EXCLUDED.price,
            coverage_area = EXCLUDED.coverage_area,
            cadr_smoke = EXCLUDED.cadr_smoke,
            cadr_pollen = EXCLUDED.cadr_pollen,
            cadr_dust = EXCLUDED.cadr_dust,
            noise_level = EXCLUDED.noise_level,
            filter_type = EXCLUDED.filter_type,
            fan_speeds = EXCLUDED.fan_speeds,
            amazon_link = EXCLUDED.amazon_link,
            updated_at = CURRENT_TIMESTAMP
        """

        try:
            with conn.cursor() as cur:
                for record in self.processed_data:
                    clean_record = record.copy()

                    # 2. 遍历所有字段，把 字典(dict) 或 列表(list) 转为 字符串
                    for key, value in clean_record.items():
                        if isinstance(value, (dict, list)):
                            # ensure_ascii=False 保证中文不会变成乱码
                            clean_record[key] = json.dumps(value, ensure_ascii=False)

                    # 3. 使用处理后的数据执行 SQL
                    cur.execute(insert_sql, clean_record)

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

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) as total FROM sylvane_products")
                total = cur.fetchone()['total']
                print(f"\n数据库中共有 {total} 条记录")

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

        # 统计价格范围
        prices = [r['price'] for r in self.processed_data if r['price']]
        if prices:
            print(f"\n价格范围:")
            print(f"  最低: ${min(prices):.2f}")
            print(f"  最高: ${max(prices):.2f}")
            print(f"  平均: ${sum(prices)/len(prices):.2f}")

        # 统计覆盖面积
        coverages = [r['coverage_area'] for r in self.processed_data if r['coverage_area']]
        if coverages:
            print(f"\n覆盖面积范围:")
            print(f"  最小: {min(coverages)} sq. ft.")
            print(f"  最大: {max(coverages)} sq. ft.")
            print(f"  平均: {sum(coverages)/len(coverages):.0f} sq. ft.")


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

    processor = SylvaneDataProcessor(
        input_file="sylvane_raw.json",
        db_config=db_config
    )

    try:
        # 1. 加载数据
        processor.load_data()

        # 2. 数据清洗
        processor.process_all()

        # 3. 保存到 JSON
        processor.save_to_json("sylvane_processed.json")

        # 4. 保存到数据库
        processor.save_to_database()

        # 5. 打印摘要
        processor.print_summary()

        print("\n处理完成!")

    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("请确保 sylvane_raw.json 文件存在于当前目录")
    except Exception as e:
        print(f"\n处理过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
