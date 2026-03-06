"""文档注册表模块。

本模块提供:
- 跟踪已索引的文档
- 使用 SHA256 哈希检测文档变更
- 增量索引支持
"""

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime


class DocumentRegistry:
    """文档注册表，用于跟踪已索引的文档。

    使用 SHA256 哈希来检测文档是否已被索引，支持增量索引。
    """

    def __init__(self, registry_path: Optional[str] = None):
        """初始化文档注册表。

        Args:
            registry_path: 注册表文件路径，默认为 data/indexed_documents.json
        """
        if registry_path is None:
            # 默认路径相对于项目根目录
            self.registry_path = Path(__file__).parent.parent / "data" / "indexed_documents.json"
        else:
            self.registry_path = Path(registry_path)

        self._registry: Dict[str, Dict[str, str]] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """从文件加载注册表。

        如果文件不存在，创建一个空的注册表。
        """
        # 确保父目录存在
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    self._registry = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"⚠️ 加载注册表失败: {e}，将创建新的注册表")
                self._registry = {}
                self._save_registry()
        else:
            # 创建新的空注册表
            self._registry = {}
            self._save_registry()

    def _save_registry(self) -> None:
        """保存注册表到文件。"""
        try:
            with open(self.registry_path, "w", encoding="utf-8") as f:
                json.dump(self._registry, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"⚠️ 保存注册表失败: {e}")

    def calculate_hash(self, file_path: str) -> str:
        """计算文件的 SHA256 哈希值。

        Args:
            file_path: 文件路径

        Returns:
            SHA256 哈希值的十六进制字符串
        """
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                # 分块读取文件以处理大文件
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except (IOError, OSError) as e:
            print(f"⚠️ 计算文件哈希失败 {file_path}: {e}")
            return ""

    def is_indexed(self, file_path: str) -> bool:
        """检查文件是否已被索引。

        Args:
            file_path: 文件路径

        Returns:
            如果文件已被索引（哈希匹配）返回 True，否则返回 False
        """
        # 规范化路径
        normalized_path = str(Path(file_path).resolve())

        # 如果文件不在注册表中，返回 False
        if normalized_path not in self._registry:
            return False

        # 计算当前文件的哈希
        current_hash = self.calculate_hash(file_path)
        if not current_hash:
            return False

        # 比较哈希值
        registered_hash = self._registry[normalized_path].get("hash", "")
        return current_hash == registered_hash

    def mark_indexed(
        self,
        file_path: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        """标记文件为已索引。

        Args:
            file_path: 文件路径
            metadata: 可选的元数据，如 chunks_count、indexed_at 等
        """
        # 规范化路径
        normalized_path = str(Path(file_path).resolve())

        # 计算文件哈希
        file_hash = self.calculate_hash(file_path)
        if not file_hash:
            print(f"⚠️ 无法计算文件哈希 {file_path}，跳过标记")
            return

        # 准备元数据
        entry_metadata = {
            "hash": file_hash,
            "indexed_at": datetime.now().isoformat(),
        }
        if metadata:
            entry_metadata.update(metadata)

        # 更新注册表
        self._registry[normalized_path] = entry_metadata

        # 保存到文件
        self._save_registry()

    def get_indexed_files(self) -> Dict[str, Dict[str, str]]:
        """获取所有已索引的文件。

        Returns:
            字典，键为文件路径，值为包含哈希和元数据的字典
        """
        return self._registry.copy()

    def remove(self, file_path: str) -> bool:
        """从注册表中移除文件。

        Args:
            file_path: 文件路径

        Returns:
            如果文件被成功移除返回 True，如果文件不存在返回 False
        """
        # 规范化路径
        normalized_path = str(Path(file_path).resolve())

        if normalized_path not in self._registry:
            return False

        del self._registry[normalized_path]
        self._save_registry()
        return True

    def get_stats(self) -> Dict[str, any]:
        """获取注册表统计信息。

        Returns:
            包含统计信息的字典
        """
        indexed_files = self.get_indexed_files()

        # 统计元数据
        total_chunks = 0
        for entry in indexed_files.values():
            chunks_count = entry.get("chunks_count", 0)
            # 处理字符串和整数类型
            if isinstance(chunks_count, str):
                try:
                    total_chunks += int(chunks_count)
                except (ValueError, TypeError):
                    pass
            elif isinstance(chunks_count, int):
                total_chunks += chunks_count

        # 获取最近的索引时间
        indexed_times = [
            entry.get("indexed_at", "")
            for entry in indexed_files.values()
            if entry.get("indexed_at")
        ]
        last_indexed = max(indexed_times) if indexed_times else None

        return {
            "total_files": len(indexed_files),
            "total_chunks": total_chunks,
            "last_indexed": last_indexed,
            "registry_path": str(self.registry_path),
        }

    def clear(self) -> None:
        """清空注册表。"""
        self._registry = {}
        self._save_registry()

    def get_modified_files(self, file_paths: List[str]) -> List[str]:
        """获取已修改的文件列表（需要重新索引）。

        Args:
            file_paths: 要检查的文件路径列表

        Returns:
            需要重新索引的文件路径列表
        """
        modified = []
        for file_path in file_paths:
            if not self.is_indexed(file_path):
                modified.append(file_path)
        return modified

    def get_file_metadata(self, file_path: str) -> Optional[Dict[str, str]]:
        """获取文件的元数据。

        Args:
            file_path: 文件路径

        Returns:
            文件的元数据字典，如果文件不存在返回 None
        """
        normalized_path = str(Path(file_path).resolve())
        return self._registry.get(normalized_path)
