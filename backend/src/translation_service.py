"""免费的翻译服务，使用现有的ZhipuAI LLM进行英法中翻译。

该服务提供：
1. 基于LLM的翻译（英/法/中互译）
2. 学校术语映射作为后备方案
3. 翻译缓存以减少API调用
4. 语言检测功能
"""

import re
import json
import hashlib
from typing import Optional, Dict, Tuple
from pathlib import Path
from datetime import datetime, timedelta

from .zhipuai_llm import ZhipuAIClient
from .school_terms import get_french_translations


class TranslationCache:
    """简单的内存翻译缓存，支持持久化。"""

    def __init__(self, cache_dir: str = "./data", max_age_hours: int = 24):
        """
        初始化翻译缓存。

        Args:
            cache_dir: 缓存目录
            max_age_hours: 缓存最大有效期（小时）
        """
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "translation_cache.json"
        self.max_age = timedelta(hours=max_age_hours)
        self.cache: Dict[str, Dict] = {}
        self._load_cache()

    def _load_cache(self):
        """从文件加载缓存。"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 过滤过期条目
                    now = datetime.now()
                    self.cache = {
                        k: v for k, v in data.items()
                        if now - datetime.fromisoformat(v["timestamp"]) < self.max_age
                    }
            except (json.JSONDecodeError, KeyError, ValueError):
                self.cache = {}

    def _save_cache(self):
        """保存缓存到文件。"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def _make_key(self, text: str, target_lang: str) -> str:
        """生成缓存键。"""
        content = f"{text}:{target_lang}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, text: str, target_lang: str) -> Optional[str]:
        """从缓存获取翻译。"""
        key = self._make_key(text, target_lang)
        entry = self.cache.get(key)
        if entry:
            # 检查是否过期
            age = datetime.now() - datetime.fromisoformat(entry["timestamp"])
            if age < self.max_age:
                return entry["translation"]
        return None

    def set(self, text: str, target_lang: str, translation: str):
        """保存翻译到缓存。"""
        key = self._make_key(text, target_lang)
        self.cache[key] = {
            "text": text,
            "target_lang": target_lang,
            "translation": translation,
            "timestamp": datetime.now().isoformat()
        }
        self._save_cache()

    def clear(self):
        """清空缓存。"""
        self.cache = {}
        if self.cache_file.exists():
            self.cache_file.unlink()


class FreeTranslationService:
    """免费的翻译服务，使用现有LLM进行翻译。

    支持英/法/中互译，当LLM不可用时使用学校术语映射作为后备。
    """

    # 语言检测模式
    CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')
    FRENCH_PATTERN = re.compile(r'[éèêëàâäùûüôöîïç]')

    def __init__(
        self,
        llm_client: Optional[ZhipuAIClient] = None,
        cache_dir: str = "./data",
        use_cache: bool = True,
    ):
        """
        初始化翻译服务。

        Args:
            llm_client: ZhipuAI客户端实例。如果为None，将创建新实例
            cache_dir: 缓存目录
            use_cache: 是否使用缓存
        """
        self.llm_client = llm_client
        self.use_cache = use_cache

        if self.use_cache:
            self.cache = TranslationCache(cache_dir=cache_dir)
        else:
            self.cache = None

    def detect_language(self, text: str) -> str:
        """
        检测文本语言。

        Args:
            text: 要检测的文本

        Returns:
            语言代码: 'zh' (中文), 'fr' (法语), 'en' (英语)
        """
        # 检查中文字符
        if self.CHINESE_PATTERN.search(text):
            return 'zh'

        # 检查法文字符
        if self.FRENCH_PATTERN.search(text):
            return 'fr'

        # 默认为英语
        return 'en'

    def _translate_with_llm(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None
    ) -> Optional[str]:
        """
        使用LLM进行翻译。

        Args:
            text: 要翻译的文本
            target_lang: 目标语言 ('zh', 'fr', 'en')
            source_lang: 源语言（可选）

        Returns:
            翻译后的文本，失败返回None
        """
        if not self.llm_client:
            return None

        # 语言名称映射
        lang_names = {
            'zh': '中文',
            'fr': '法语',
            'en': '英语'
        }

        target_name = lang_names.get(target_lang, target_lang)
        source_name = lang_names.get(source_lang, '自动检测') if source_lang else '自动检测'

        # 构建翻译提示词
        prompt = f"""请将以下文本翻译成{target_name}。只返回翻译结果，不要添加任何解释。

文本：{text}

翻译："""

        try:
            result = self.llm_client.chat(
                prompt=prompt,
                temperature=0.3,  # 使用较低温度以获得更准确的翻译
            )

            if result["success"]:
                translation = result["response"].strip()
                # 清理可能的引号或多余字符
                translation = translation.strip('"\'')

                return translation

        except Exception as e:
            print(f"LLM翻译失败: {e}")

        return None

    def _translate_with_fallback(
        self,
        text: str,
        target_lang: str,
        source_lang: str
    ) -> Optional[str]:
        """
        使用学校术语映射作为后备翻译。

        仅支持英语到法语的简单术语翻译。

        Args:
            text: 要翻译的文本
            target_lang: 目标语言
            source_lang: 源语言

        Returns:
            翻译后的文本（如果可用）
        """
        # 仅支持英语到法语的后备翻译
        if source_lang == 'en' and target_lang == 'fr':
            text_lower = text.lower()
            translated = text_lower

            # 查找并替换已知术语
            from school_terms import SECONDARY_SCHOOL_TERMS
            for en_term, fr_terms in SECONDARY_SCHOOL_TERMS.items():
                if en_term in translated:
                    # 使用第一个法语翻译
                    translated = translated.replace(en_term, fr_terms[0])

            # 如果发生了替换，返回翻译结果
            if translated != text_lower:
                return translated

        return None

    def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None,
        use_fallback: bool = True
    ) -> Tuple[str, Optional[str]]:
        """
        翻译文本到目标语言。

        Args:
            text: 要翻译的文本
            target_lang: 目标语言代码 ('zh', 'fr', 'en')
            source_lang: 源语言代码（可选，自动检测）
            use_fallback: 是否使用后备翻译

        Returns:
            元组：(翻译后的文本, 实际使用的源语言)
            如果翻译失败，返回 (原文本, 检测到的语言)
        """
        if not text or not text.strip():
            return text, None

        # 检测源语言
        detected_lang = self.detect_language(text)
        source_lang = source_lang or detected_lang

        # 如果源语言和目标语言相同，直接返回
        if source_lang == target_lang:
            return text, source_lang

        # 检查缓存
        if self.cache:
            cached = self.cache.get(text, target_lang)
            if cached:
                return cached, source_lang

        # 尝试LLM翻译
        translation = None
        if self.llm_client:
            translation = self._translate_with_llm(text, target_lang, source_lang)

        # 如果LLM翻译失败且启用后备方案
        if not translation and use_fallback:
            translation = self._translate_with_fallback(text, target_lang, source_lang)

        # 如果所有翻译都失败，返回原文本
        if not translation:
            return text, source_lang

        # 保存到缓存
        if self.cache:
            self.cache.set(text, target_lang, translation)

        return translation, source_lang

    def translate_to_french(self, text: str) -> str:
        """翻译文本到法语。"""
        translation, _ = self.translate(text, 'fr')
        return translation

    def translate_to_english(self, text: str) -> str:
        """翻译文本到英语。"""
        translation, _ = self.translate(text, 'en')
        return translation

    def translate_to_chinese(self, text: str) -> str:
        """翻译文本到中文。"""
        translation, _ = self.translate(text, 'zh')
        return translation


def detect_language(text: str) -> str:
    """
    检测文本语言的便捷函数。

    Args:
        text: 要检测的文本

    Returns:
        语言代码: 'zh', 'fr', 或 'en'
    """
    service = FreeTranslationService(llm_client=None, use_cache=False)
    return service.detect_language(text)
