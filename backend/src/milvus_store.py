"""Milvus 向量数据库存储包装器。

本模块提供:
- Milvus 连接管理
- 集合的创建和管理
- 文档向量的插入和搜索
- 健康检查功能
"""

import time
from typing import List, Dict, Any, Optional, Tuple
from pymilvus import (
    connections,
    Collection,
    FieldSchema,
    CollectionSchema,
    DataType,
    utility,
)
from pymilvus.exceptions import MilvusException
import numpy as np


class MilvusStore:
    """Milvus 向量存储包装器，用于文档检索和相似性搜索。

    使用 HNSW 索引和余弦相似度进行高效的向量搜索。
    """

    # BGE-M3 embedding 维度
    EMBEDDING_DIM = 1024

    # 默认配置
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 19530
    DEFAULT_COLLECTION_NAME = "documents"

    # HNSW 索引参数
    HNSW_INDEX_TYPE = "HNSW"
    HNSW_METRIC_TYPE = "COSINE"
    HNSW_PARAMS = {
        "M": 16,  # HNSW 图的连接数，越大召回率越高但内存消耗也越大
        "efConstruction": 256,  # 构建索引时的搜索范围
    }

    # 搜索参数
    SEARCH_PARAMS = {"metric_type": HNSW_METRIC_TYPE, "params": {"ef": 32}}

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        reset: bool = False,
    ):
        """初始化 Milvus 存储连接。

        Args:
            host: Milvus 服务器地址
            port: Milvus 服务器端口
            collection_name: 集合名称
            reset: 如果为 True，删除并重新创建集合
        """
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.reset = reset

        self._connected = False
        self._collection: Optional[Collection] = None
        self._healthy = True
        self._last_error: Optional[str] = None

        # 初始化连接
        self._connect()

        # 如果需要重置，删除现有集合
        if reset and self.has_collection():
            self.drop_collection()

        # 加载或创建集合
        if self.has_collection():
            self.load_collection()
        else:
            self.create_collection()

    def _connect(self) -> bool:
        """连接到 Milvus 服务器。

        Returns:
            连接成功返回 True，否则返回 False
        """
        try:
            # 使用 alias "default" 进行连接
            if connections.has_connection("default"):
                connections.disconnect("default")

            connections.connect(
                alias="default",
                host=self.host,
                port=self.port,
            )

            # 测试连接
            connections.list_connections()

            self._connected = True
            self._healthy = True
            self._last_error = None
            return True

        except MilvusException as e:
            self._connected = False
            self._healthy = False
            self._last_error = str(e)
            print(f"⚠️ Milvus 连接错误: {e}")
            return False

    def disconnect(self):
        """断开与 Milvus 的连接。"""
        try:
            if connections.has_connection("default"):
                connections.disconnect("default")
            self._connected = False
        except MilvusException as e:
            print(f"⚠️ 断开 Milvus 连接时出错: {e}")

    def has_collection(self) -> bool:
        """检查集合是否存在。

        Returns:
            集合存在返回 True，否则返回 False
        """
        try:
            return utility.has_collection(self.collection_name)
        except MilvusException as e:
            self._healthy = False
            self._last_error = str(e)
            print(f"⚠️ 检查集合是否存在时出错: {e}")
            return False

    def create_collection(self) -> bool:
        """创建 Milvus 集合。

        定义集合 schema 并创建 HNSW 索引。

        Returns:
            创建成功返回 True，否则返回 False
        """
        try:
            # 定义字段 schema
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=256),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.EMBEDDING_DIM),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=512),
                FieldSchema(name="page", dtype=DataType.INT64),
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(name="date", dtype=DataType.VARCHAR, max_length=64),
            ]

            # 创建集合 schema
            schema = CollectionSchema(
                fields=fields,
                description="Document chunks with embeddings for RAG",
                enable_dynamic_field=True,  # 允许动态字段
            )

            # 创建集合
            self._collection = Collection(
                name=self.collection_name,
                schema=schema,
            )

            # 创建 HNSW 索引
            index_params = {
                "index_type": self.HNSW_INDEX_TYPE,
                "metric_type": self.HNSW_METRIC_TYPE,
                "params": self.HNSW_PARAMS,
            }

            self._collection.create_index(
                field_name="embedding",
                index_params=index_params,
            )

            self._healthy = True
            self._last_error = None
            print(f"✅ 创建 Milvus 集合 '{self.collection_name}' 成功")
            return True

        except MilvusException as e:
            self._healthy = False
            self._last_error = str(e)
            print(f"⚠️ 创建 Milvus 集合时出错: {e}")
            return False

    def load_collection(self) -> bool:
        """加载现有集合到内存。

        Returns:
            加载成功返回 True，否则返回 False
        """
        try:
            self._collection = Collection(self.collection_name)
            self._collection.load()

            self._healthy = True
            self._last_error = None
            print(f"✅ 加载 Milvus 集合 '{self.collection_name}' 成功")
            return True

        except MilvusException as e:
            self._healthy = False
            self._last_error = str(e)
            print(f"⚠️ 加载 Milvus 集合时出错: {e}")
            return False

    def drop_collection(self) -> bool:
        """删除集合。

        Returns:
            删除成功返回 True，否则返回 False
        """
        try:
            if self.has_collection():
                utility.drop_collection(self.collection_name)
                self._collection = None
                print(f"✅ 删除 Milvus 集合 '{self.collection_name}' 成功")
            return True

        except MilvusException as e:
            self._healthy = False
            self._last_error = str(e)
            print(f"⚠️ 删除 Milvus 集合时出错: {e}")
            return False

    def insert(
        self,
        ids: List[str],
        embeddings: np.ndarray,
        contents: List[str],
        sources: List[str],
        pages: List[int],
        chunk_indices: List[int],
        dates: List[str],
        **kwargs,
    ) -> int:
        """插入文档块到集合。

        Args:
            ids: 文档块 ID 列表
            embeddings: 嵌入向量数组，shape (n, EMBEDDING_DIM)
            contents: 文档内容列表
            sources: 来源文件列表
            pages: 页码列表
            chunk_indices: 块索引列表
            dates: 日期列表
            **kwargs: 额外的动态字段

        Returns:
            插入的文档块数量
        """
        if self._collection is None:
            print("⚠️ 集合未初始化，跳过插入操作")
            return 0

        # 处理空数据
        if len(ids) == 0:
            return 0

        try:
            # 准备数据
            data = [
                ids,
                embeddings.tolist() if isinstance(embeddings, np.ndarray) else embeddings,
                contents,
                sources,
                pages,
                chunk_indices,
                dates,
            ]

            # 插入数据
            insert_result = self._collection.insert(data)

            # 刷新以确保数据持久化
            self._collection.flush()

            # 重新加载集合以确保新数据可被搜索
            # Milvus 需要在插入后重新加载才能搜索到新数据
            self._collection.load(_resource_ids=[insert_result.primary_keys])

            self._healthy = True
            self._last_error = None
            return len(ids)

        except MilvusException as e:
            self._healthy = False
            self._last_error = str(e)
            print(f"⚠️ 插入数据到 Milvus 时出错: {e}")
            return 0

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """搜索相似的文档块。

        Args:
            query_embedding: 查询嵌入向量，shape (EMBEDDING_DIM,)
            top_k: 返回的结果数量
            expr: 过滤表达式（可选）

        Returns:
            搜索结果列表，每个结果包含 id, content, score, metadata
        """
        if self._collection is None:
            print("⚠️ 集合未初始化，返回空结果")
            return []

        try:
            # 确保 query_embedding 是二维数组
            if query_embedding.ndim == 1:
                query_embedding = query_embedding.reshape(1, -1)

            # 执行搜索
            results = self._collection.search(
                data=query_embedding.tolist(),
                anns_field="embedding",
                param=self.SEARCH_PARAMS,
                limit=top_k,
                expr=expr,
                output_fields=["content", "source", "page", "chunk_index", "date"],
            )

            # 格式化结果
            output = []
            for hit in results[0]:
                output.append({
                    "id": hit.id,
                    "content": hit.entity.get("content", ""),
                    "score": float(hit.score),  # 余弦相似度，范围 [0, 1]
                    "metadata": {
                        "source": hit.entity.get("source", ""),
                        "page": hit.entity.get("page", 0),
                        "chunk_index": hit.entity.get("chunk_index", 0),
                        "date": hit.entity.get("date", ""),
                    },
                })

            self._healthy = True
            self._last_error = None
            return output

        except MilvusException as e:
            self._healthy = False
            self._last_error = str(e)
            print(f"⚠️ 在 Milvus 中搜索时出错: {e}")
            return []

    def search_timed(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        expr: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], float]:
        """带计时的搜索。

        Returns:
            元组 (搜索结果, 耗时毫秒)
        """
        start = time.time()
        results = self.search(query_embedding, top_k, expr)
        elapsed_ms = (time.time() - start) * 1000
        return results, elapsed_ms

    def get_count(self) -> int:
        """获取集合中的文档块数量。

        Returns:
            文档块数量，出错时返回 0
        """
        if self._collection is None:
            return 0

        try:
            return self._collection.num_entities
        except MilvusException as e:
            self._healthy = False
            self._last_error = str(e)
            print(f"⚠️ 获取 Milvus 集合计数时出错: {e}")
            return 0

    def is_healthy(self) -> bool:
        """检查存储是否健康。

        Returns:
            健康返回 True，否则返回 False
        """
        return self._healthy

    def get_unique_sources(self) -> List[str]:
        """获取所有唯一的源文件名。

        Returns:
            唯一源文件名列表
        """
        if self._collection is None:
            return []

        try:
            # Query to get all unique sources
            results = self._collection.query(
                expr="source != ''",
                output_fields=["source"],
                limit=10000
            )

            # Extract unique sources
            unique_sources = set()
            for r in results:
                if "source" in r and r["source"]:
                    unique_sources.add(r["source"])

            return sorted(list(unique_sources))

        except MilvusException as e:
            self._healthy = False
            self._last_error = str(e)
            print(f"⚠️ 获取唯一源时出错: {e}")
            return []

    def get_collection_info(self) -> Dict[str, Any]:
        """获取集合的详细信息。

        Returns:
            包含集合信息的字典
        """
        if self._collection is None:
            return {}

        try:
            from pymilvus import utility

            info = {
                "name": self._collection.name,
                "num_entities": self._collection.num_entities,
                "description": self._collection.description,
                "index_type": "HNSW",  # Default, we use HNSW index
                "metric_type": "COSINE",  # Default, we use COSINE similarity
                "embedding_dim": 1024,  # Default for BGE-M3
            }

            # Try to get more accurate index info
            try:
                indexes = utility.list_indexes(self.collection_name)
                if indexes:
                    for index_name in indexes:
                        index_obj = self._collection.index(index_name)
                        if index_obj:
                            info["index_type"] = index_obj.params.get("index_type", "HNSW")
                            info["metric_type"] = index_obj.params.get("metric_type", "COSINE")
                            break
            except Exception:
                pass  # Use defaults

            # Get embedding dimension from schema
            try:
                schema = self._collection.schema
                for field in schema.fields:
                    if field.name == "embedding":
                        # Get vector dimension from params
                        if hasattr(field.dtype, '__len__'):
                            info["embedding_dim"] = field.dtype[1] if len(field.dtype) > 1 else 1024
                        break
            except Exception:
                pass  # Use default

            return info

        except MilvusException as e:
            self._healthy = False
            self._last_error = str(e)
            print(f"⚠️ 获取集合信息时出错: {e}")
            return {
                "index_type": "HNSW",
                "metric_type": "COSINE",
                "embedding_dim": 1024,
            }

    def health_check(self) -> Dict[str, Any]:
        """执行健康检查。

        Returns:
            包含健康状态和详细信息的字典
        """
        result = {
            "healthy": self._healthy,
            "connected": self._connected,
            "collection_exists": False,
            "collection_loaded": False,
            "document_count": 0,
            "last_error": self._last_error,
            "host": self.host,
            "port": self.port,
            "collection_name": self.collection_name,
        }

        try:
            # 检查连接
            if not self._connected:
                self._connect()

            result["connected"] = self._connected

            if not self._connected:
                return result

            # 检查集合是否存在
            result["collection_exists"] = self.has_collection()

            if not result["collection_exists"]:
                return result

            # 检查集合是否已加载
            if self._collection is None:
                self.load_collection()

            result["collection_loaded"] = self._collection is not None

            # 获取文档数量和唯一源数量
            if result["collection_loaded"]:
                count = self.get_count()
                result["document_count"] = count
                result["count"] = count  # API compatibility
                result["healthy"] = True

                # 获取唯一源数量
                try:
                    unique_sources = self.get_unique_sources()
                    result["unique_sources"] = len(unique_sources)
                except Exception:
                    result["unique_sources"] = 0

        except Exception as e:
            result["last_error"] = str(e)
            result["healthy"] = False

        return result

    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计信息。

        Returns:
            包含统计信息的字典
        """
        health = self.health_check()

        return {
            "chunk_count": health["document_count"],
            "collection_name": self.collection_name,
            "host": self.host,
            "port": self.port,
            "embedding_dim": self.EMBEDDING_DIM,
            "index_type": self.HNSW_INDEX_TYPE,
            "metric_type": self.HNSW_METRIC_TYPE,
            "healthy": health["healthy"],
            "connected": health["connected"],
            "last_error": self._last_error,
        }


# 便捷函数
def create_milvus_store(
    host: str = MilvusStore.DEFAULT_HOST,
    port: int = MilvusStore.DEFAULT_PORT,
    collection_name: str = MilvusStore.DEFAULT_COLLECTION_NAME,
    reset: bool = False,
) -> MilvusStore:
    """创建 Milvus 存储实例的便捷函数。

    Args:
        host: Milvus 服务器地址
        port: Milvus 服务器端口
        collection_name: 集合名称
        reset: 是否重置集合

    Returns:
        MilvusStore 实例
    """
    return MilvusStore(
        host=host,
        port=port,
        collection_name=collection_name,
        reset=reset,
    )
