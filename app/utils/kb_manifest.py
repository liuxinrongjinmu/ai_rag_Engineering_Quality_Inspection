"""
知识库文件清单管理模块
通过 MD5 哈希追踪 data/processed/ 中每个文件的处理状态，
实现增量同步：只处理新增/修改/删除的文件，跳过未变化的文件。
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class SyncPlan:
    """
    增量同步计划：分类汇总变更文件
    """
    new_files: List[Path] = field(default_factory=list)
    modified_files: List[Path] = field(default_factory=list)
    deleted_files: List[str] = field(default_factory=list)  # doc_id 列表
    unchanged_count: int = 0

    @property
    def total_changes(self) -> int:
        return len(self.new_files) + len(self.modified_files) + len(self.deleted_files)

    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0


class KBManifest:
    """
    知识库文件清单管理器
    以 JSON 文件持久化文件哈希和同步状态
    """

    def __init__(self, data_dir: str):
        """
        初始化清单管理器

        :param data_dir: 数据目录路径（data/processed/）
        """
        self.data_dir = Path(data_dir)
        self.manifest_path = self.data_dir / "kb_manifest.json"
        self._manifest: Dict[str, dict] = {}
        self._loaded = False

    def _load(self) -> Dict[str, dict]:
        """
        加载清单文件

        :return: 清单字典 {filename: {hash, doc_id, synced_at}}
        """
        if self._loaded:
            return self._manifest

        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._manifest = data.get("files", {})
                logger.info(f"清单已加载: {len(self._manifest)}个文件记录")
            except Exception as e:
                logger.warning(f"清单加载失败，将重建: {e}")
                self._manifest = {}

        self._loaded = True
        return self._manifest

    def _save(self) -> None:
        """保存清单到文件"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "updated_at": "",
            "files": self._manifest,
        }
        from datetime import datetime
        data["updated_at"] = datetime.now().isoformat()

        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _compute_file_hash(file_path: Path) -> str:
        """
        计算文件的 MD5 哈希

        :param file_path: 文件路径
        :return: 32位十六进制哈希
        """
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _get_doc_id(file_path: Path) -> str:
        """
        根据文件名生成 doc_id（与 document_loaders 保持一致）

        :param file_path: 文件路径
        :return: 16位hex doc_id
        """
        return hashlib.md5(file_path.name.encode()).hexdigest()[:16]

    def compute_plan(
        self,
        allowed_extensions: set,
    ) -> SyncPlan:
        """
        扫描数据目录，对比清单，生成增量同步计划

        :param allowed_extensions: 允许的文件扩展名集合
        :return: SyncPlan 对象
        """
        manifest = self._load()
        plan = SyncPlan()

        # 收集磁盘上的文件
        disk_files: Dict[str, Path] = {}
        for ext in allowed_extensions:
            for f in self.data_dir.glob(f"*{ext}"):
                disk_files[f.name] = f
        # 排除清单文件自身
        disk_files.pop("kb_manifest.json", None)

        # 检测新增和修改
        for filename, file_path in disk_files.items():
            current_hash = self._compute_file_hash(file_path)
            entry = manifest.get(filename)

            if entry is None:
                # 新文件
                plan.new_files.append(file_path)
                logger.info(f"  [新增] {filename}")
            elif entry.get("hash") != current_hash:
                # 文件内容已变更
                plan.modified_files.append(file_path)
                logger.info(f"  [修改] {filename}")
            else:
                plan.unchanged_count += 1

        # 检测删除（在清单中但磁盘上不存在）
        for filename, entry in manifest.items():
            if filename not in disk_files:
                doc_id = entry.get("doc_id", "")
                plan.deleted_files.append(doc_id)
                logger.info(f"  [删除] {filename} (doc_id={doc_id})")

        if plan.has_changes:
            logger.info(
                f"同步计划: 新增{len(plan.new_files)} 修改{len(plan.modified_files)} "
                f"删除{len(plan.deleted_files)} 未变化{plan.unchanged_count}"
            )
        else:
            logger.info(f"无变更，{plan.unchanged_count}个文件均为最新")

        return plan

    def update_entry(self, file_path: Path) -> dict:
        """
        更新单个文件的清单记录（处理完成后调用）

        :param file_path: 文件路径
        :return: 更新的记录
        """
        from datetime import datetime

        entry = {
            "hash": self._compute_file_hash(file_path),
            "doc_id": self._get_doc_id(file_path),
            "synced_at": datetime.now().isoformat(),
        }
        self._manifest[file_path.name] = entry
        return entry

    def remove_entry(self, filename: str) -> None:
        """
        从清单中移除文件记录

        :param filename: 文件名
        """
        self._manifest.pop(filename, None)

    def flush(self) -> None:
        """持久化清单到磁盘"""
        self._save()
        logger.info(f"清单已保存: {len(self._manifest)}个文件记录")


def get_manifest(data_dir: str) -> KBManifest:
    """
    获取 KBManifest 实例

    :param data_dir: 数据目录路径
    :return: KBManifest 实例
    """
    return KBManifest(data_dir)
