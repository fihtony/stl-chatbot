"""日期提取和解析工具。

从文档文件名和内容中提取日期信息，用于按时间排序结果。
"""

import re
from datetime import datetime
from typing import Optional, Tuple
from pathlib import Path


# French month names
FRENCH_MONTHS = {
    'janvier': 1, 'février': 2, 'fevrier': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8, 'aout': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12, 'decembre': 12
}

# English month names
ENGLISH_MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5,
    'june': 6, 'july': 7, 'august': 8, 'september': 9, 'october': 10,
    'november': 11, 'december': 12
}

# All month names
ALL_MONTHS = {**FRENCH_MONTHS, **ENGLISH_MONTHS}


def extract_date_from_filename(filename: str) -> Optional[Tuple[datetime, str]]:
    """从文件名中提取日期。

    支持的格式：
    - Info-parents_de_mars_2026.pdf → (2026-03-01, "mars 2026")
    - Info-parents-de-fevrier-2026.pdf → (2026-02-01, "fevrier 2026")
    - info-parents-janvier-2026.txt → (2026-01-01, "janvier 2026")

    Args:
        filename: 文件名

    Returns:
        (日期对象, 月份字符串) 或 None
    """
    if not filename:
        return None

    filename_lower = filename.lower()

    # 模式 1: {month}_{year} 或 {month}-{year}
    # 例如: mars_2026, fevrier-2026
    for month_name, month_num in ALL_MONTHS.items():
        # 匹配 mars_2026, fevrier_2026, etc.
        pattern = rf'{month_name}[_-](\d{{4}})'
        match = re.search(pattern, filename_lower)
        if match:
            year = int(match.group(1))
            try:
                date_obj = datetime(year, month_num, 1)
                return (date_obj, f"{month_name} {year}")
            except ValueError:
                continue

    # 模式 2: {month}{year} 或 {month}-{year}（无分隔符）
    # 例如: mars2026, fevrier2026
    for month_name, month_num in ALL_MONTHS.items():
        pattern = rf'{month_name}(\d{{4}})'
        match = re.search(pattern, filename_lower)
        if match:
            year = int(match.group(1))
            try:
                date_obj = datetime(year, month_num, 1)
                return (date_obj, f"{month_name} {year}")
            except ValueError:
                continue

    # 模式 3: YYYY-MM-DD 或 YYYY/MM/DD
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', filename)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            date_obj = datetime(year, month, day)
            # 找到对应的月份名称
            month_name = ALL_MONTHS.get(date_obj.strftime('%B').lower(), str(month_num))
            return (date_obj, f"{month_name} {year}")
        except ValueError:
            pass

    # 模式 4: Info-parents-de-{month}-{year}
    # 例如: Info-parents-de-mars-2026
    match = re.search(r'info-parents[_-]de[_-](\w+)[_-](\d{4})', filename_lower)
    if match:
        month_name = match.group(1)
        year_str = match.group(2)
        month_num = ALL_MONTHS.get(month_name)
        if month_num and year_str.isdigit():
            year = int(year_str)
            try:
                date_obj = datetime(year, month_num, 1)
                return (date_obj, f"{month_name} {year}")
            except ValueError:
                pass

    return None


def extract_date_from_content(content: str, filename: str = "") -> Optional[Tuple[datetime, str]]:
    """从文档内容中提取日期。

    在内容中搜索日期模式，优先选择最新日期。

    Args:
        content: 文档内容
        filename: 文件名（用于回退）

    Returns:
        (日期对象, 来源描述) 或 None
    """
    if not content:
        return extract_date_from_filename(filename)

    # 首先尝试从文件名提取
    filename_date = extract_date_from_filename(filename)

    # 在内容中搜索日期
    dates_found = []

    # 模式: "Info-parents {month} {year}"
    for month_name, month_num in ALL_MONTHS.items():
        pattern = rf'info-parents\s+{month_name}\s+(\d{{4}})'
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            year = int(match.group(1))
            try:
                date_obj = datetime(year, month_num, 1)
                dates_found.append((date_obj, f"{month_name} {year}"))
            except ValueError:
                continue

    # 模式: "{month} {year}" (在标题中)
    for month_name, month_num in ALL_MONTHS.items():
        pattern = rf'{month_name}\s+(\d{{4}})\b'
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            year = int(match.group(1))
            try:
                date_obj = datetime(year, month_num, 1)
                dates_found.append((date_obj, f"{month_name} {year}"))
            except ValueError:
                continue

    # 返回最新的日期
    if dates_found:
        dates_found.sort(reverse=True)
        return dates_found[0]

    # 回退到文件名提取
    return filename_date


def parse_document_date(file_path: str, content: str = "") -> Optional[datetime]:
    """解析文档的日期。

    优先从文件名提取，回退到内容提取。

    Args:
        file_path: 文件路径
        content: 文档内容（可选）

    Returns:
        日期对象或 None
    """
    filename = Path(file_path).name

    # 首先从文件名提取
    result = extract_date_from_filename(filename)
    if result:
        return result[0]

    # 如果有内容，从内容提取
    if content:
        result = extract_date_from_content(content, filename)
        if result:
            return result[0]

    return None


def get_month_order(month_name: str) -> int:
    """获取月份的排序顺序（1-12）。

    Args:
        month_name: 月份名称（法语或英语）

    Returns:
        月份序号（1-12）或 0
    """
    month_lower = month_name.lower()
    return ALL_MONTHS.get(month_lower, 0)


def compare_dates(date_str1: str, date_str2: str) -> int:
    """比较两个日期字符串。

    格式: "{month} {year}" 例如 "mars 2026"

    Args:
        date_str1: 第一个日期字符串
        date_str2: 第二个日期字符串

    Returns:
        -1 如果 date_str1 < date_str2 (更早)
        0 如果 date_str1 == date_str2
        1 如果 date_str1 > date_str2 (更晚)
    """
    # 解析日期字符串
    def parse_date_str(date_str):
        parts = date_str.lower().split()
        if len(parts) == 2:
            month_name, year = parts
            month_num = ALL_MONTHS.get(month_name, 0)
            if month_num and year.isdigit():
                return (int(year), month_num)
        return (0, 0)

    year1, month1 = parse_date_str(date_str1)
    year2, month2 = parse_date_str(date_str2)

    if year1 != year2:
        return year1 - year2
    return month1 - month2


def is_later_date(date_str1: str, date_str2: str) -> bool:
    """判断 date_str1 是否比 date_str2 更晚。

    Args:
        date_str1: 第一个日期字符串
        date_str2: 第二个日期字符串

    Returns:
        True 如果 date_str1 更晚
    """
    return compare_dates(date_str1, date_str2) > 0


# Month number to French name mapping
MONTH_NUM_TO_FRENCH = {
    1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
    5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
    9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
}

MONTH_NUM_TO_ENGLISH = {
    1: 'January', 2: 'February', 3: 'March', 4: 'April',
    5: 'May', 6: 'June', 7: 'July', 8: 'August',
    9: 'September', 10: 'October', 11: 'November', 12: 'December'
}


def format_date_for_display(date_obj: datetime, language: str = 'fr') -> str:
    """格式化日期用于显示。

    Args:
        date_obj: 日期对象
        language: 语言代码 ('fr', 'en')

    Returns:
        格式化的日期字符串
    """
    if language == 'fr':
        return f"{MONTH_NUM_TO_FRENCH[date_obj.month]} {date_obj.year}"
    else:
        return f"{MONTH_NUM_TO_ENGLISH[date_obj.month]} {date_obj.year}"


def format_iso_datetime(iso_string: str, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    """格式化 ISO 日期时间字符串。

    Args:
        iso_string: ISO 格式的日期时间字符串 (例如: "2026-03-05T21:38:48")
        format_str: 输出格式字符串 (默认: '%Y-%m-%d %H:%M:%S')

    Returns:
        格式化的日期字符串，如果解析失败则返回原始字符串
    """
    try:
        dt = datetime.fromisoformat(iso_string)
        return dt.strftime(format_str)
    except (ValueError, TypeError):
        return iso_string


def format_iso_datetime_short(iso_string: str) -> str:
    """格式化 ISO 日期时间字符串为简短格式 (YYYY-MM-DD HH:MM)。

    Args:
        iso_string: ISO 格式的日期时间字符串

    Returns:
        格式化的日期字符串 (例如: "2026-03-05 21:38")
    """
    return format_iso_datetime(iso_string, '%Y-%m-%d %H:%M')
