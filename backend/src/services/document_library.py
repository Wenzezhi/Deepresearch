
"""本地文献导入、文本提取、分块与检索模块。"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from storage import Store

# 单个文件最大 25 MB
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# 单个文档最多提取 500 万字符
MAX_EXTRACTED_CHARS = 5_000_000

# 允许上传的文件类型
ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md", ".markdown"
}

# 文本分块参数
CHUNK_SIZE = 2200
CHUNK_OVERLAP = 260


class DuplicateDocumentError(ValueError):
    """重复文献异常。"""

    def __init__(self, document: dict):
        super().__init__("该文件已经在本地资料库中")
        self.document = document


class DocumentLibrary:
    """负责本地文献的解析、存储和检索。"""

    def __init__(
        self,
        store: Store,
        storage_dir: str | Path | None = None
    ):
        self.store = store

        # 原始文件存储位置
        self.storage_dir = Path(
            storage_dir or (store.path.parent / "library_files")
        )

        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def add_bytes(self, filename: str, content: bytes) -> dict:
        """导入一个文献文件。"""

        if not content:
            raise ValueError("上传文件为空")

        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("单个文件不能超过 25 MB")

        safe_name = Path(
            (filename or "").replace("\\", "/")
        ).name.strip()

        if not safe_name:
            raise ValueError("文件名无效")

        extension = Path(safe_name).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError(
                "仅支持 PDF、DOCX、TXT、Markdown 文件"
            )

        # SHA256 检测重复文件
        digest = hashlib.sha256(content).hexdigest()

        duplicate = self.store.find_document_by_hash(digest)

        if duplicate:
            raise DuplicateDocumentError(duplicate)

        # 提取文件内容
        pages, page_count = self._extract(extension, content)

        total_text = sum(len(text) for _, text in pages)

        if total_text > MAX_EXTRACTED_CHARS:
            raise ValueError(
                "文档提取文本超过 500 万字符，请拆分后再导入"
            )

        if total_text < 20:
            raise ValueError(
                "未提取到足够的正文文本；"
                "如果这是扫描版 PDF，目前需要先进行 OCR 文字识别"
            )

        # 文本分块
        chunks = self._chunk_pages(pages)

        if not chunks:
            raise ValueError("文档没有可索引的文本内容")

        document_id = uuid4().hex

        stored_name = f"{document_id}{extension}"

        stored_path = self.storage_dir / stored_name

        stored_path.write_bytes(content)

        # 保存文献元数据
        record = {
            "id": document_id,
            "title": safe_name,
            "original_name": safe_name,
            "extension": extension,
            "mime_type": self._mime_type(extension),
            "size_bytes": len(content),
            "sha256": digest,
            "text_length": total_text,
            "chunk_count": len(chunks),
            "page_count": page_count,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "stored_path": str(stored_path),
        }

        try:
            self.store.save_document(record, chunks)
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise

        return self.public_record(record)

    @staticmethod
    def public_record(record: dict) -> dict:
        """返回安全的文献元数据。"""

        return {
            key: value
            for key, value in record.items()
            if key not in {"stored_path", "sha256"}
        }

    def list_documents(self) -> list[dict]:
        """获取资料库文献列表。"""

        return [
            self.public_record(item)
            for item in self.store.documents()
        ]

    def get_document(self, identifier: str) -> dict:
        return self.store.document(identifier)

    def delete_document(self, identifier: str) -> None:
        """删除文献及其索引。"""

        protected_statuses = {
            "running", "paused", "interrupted",
            "failed", "partial"
        }

        # 防止删除仍然被未完成研究引用的文献
        for run in self.store.runs():
            if (
                run.get("status") in protected_statuses
                and identifier in (run.get("document_ids") or [])
            ):
                raise ValueError(
                    "该文献仍被未完成或可重试的研究记录引用，"
                    "请先完成或删除对应研究记录"
                )

        record = self.store.delete_document(identifier)

        path = Path(record.get("stored_path", ""))

        if path.parent.resolve() == self.storage_dir.resolve():
            path.unlink(missing_ok=True)

    def search(
        self,
        query: str,
        document_ids: list[str] | None = None,
        top_k: int = 6
    ) -> list[dict]:
        """使用 BM25 风格的关键词相关性评分召回文献片段。"""

        if not document_ids or not query.strip():
            return []

        rows = self.store.document_chunks(document_ids)

        if not rows:
            return []

        query_tokens = self._tokens(query)

        if not query_tokens:
            return []

        query_set = set(query_tokens)

        tokenized = [
            self._tokens(row["content"])
            for row in rows
        ]

        document_frequency = {}

        for tokens in tokenized:
            for token in set(tokens):
                document_frequency[token] = (
                    document_frequency.get(token, 0) + 1
                )

        count = len(rows)

        average_length = max(
            1.0,
            sum(len(tokens) for tokens in tokenized) / count
        )

        scored = []

        query_phrase = re.sub(
            r"\s+", "", query
        ).casefold()

        for row, tokens in zip(rows, tokenized):

            frequencies = {}

            for token in tokens:
                frequencies[token] = (
                    frequencies.get(token, 0) + 1
                )

            length = len(tokens)

            score = 0.0

            for token in query_set:

                frequency = frequencies.get(token, 0)

                if not frequency:
                    continue

                df = document_frequency.get(token, 0)

                inverse_frequency = math.log(
                    1 + (count - df + 0.5) / (df + 0.5)
                )

                denominator = (
                    frequency
                    + 1.2 * (
                        0.25
                        + 0.75 * length / average_length
                    )
                )

                score += (
                    inverse_frequency
                    * (frequency * 2.2)
                    / denominator
                )

            compact_content = re.sub(
                r"\s+", "", row["content"]
            ).casefold()

            if (
                len(query_phrase) >= 4
                and query_phrase in compact_content
            ):
                score += 2.0

            if score <= 0:
                continue

            document = row["document"]

            scored.append({
                "document_id": row["document_id"],
                "document_title": (
                    document.get("title")
                    or document.get("original_name")
                ),
                "page_start": row.get("page_start"),
                "page_end": row.get("page_end"),
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "score": round(score, 4),
            })

        scored.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        results = []
        per_document = {}

        for item in scored:

            identifier = item["document_id"]

            if per_document.get(identifier, 0) >= 3:
                continue

            results.append(item)

            per_document[identifier] = (
                per_document.get(identifier, 0) + 1
            )

            if len(results) >= max(1, min(top_k, 12)):
                break

        return results

    @staticmethod
    def format_context(hits: list[dict]) -> tuple[str, str]:
        """生成送给模型的上下文和来源列表。"""

        if not hits:
            return "", ""

        context_blocks = [
            "以下内容来自用户上传的本地文献。"
            "引用时请保留对应的本地文献编号；"
            "不要把文献未提及的信息归因于该文献。"
        ]

        source_lines = []

        seen = set()

        for hit in hits:

            citation_id = (
                f"D-{hit['document_id'][:8]}"
            )

            page = hit.get("page_start")

            page_label = (
                f"第 {page} 页"
                if page else "页码未标注"
            )

            context_blocks.append(
                f"[{citation_id} | "
                f"{hit['document_title']} | "
                f"{page_label}]\n"
                f"{hit['content']}"
            )

            if citation_id not in seen:

                source_lines.append(
                    f"* [本地文献 {citation_id}] "
                    f"{hit['document_title']} : "
                    f"local://documents/{hit['document_id']}"
                )

                seen.add(citation_id)

        return (
            "\n\n".join(context_blocks),
            "\n".join(source_lines)
        )

    @staticmethod
    def _tokens(text: str) -> list[str]:
        """中英文混合分词。"""

        tokens = []

        for part in re.findall(
            r"[A-Za-z0-9][A-Za-z0-9._+-]*|[\u4e00-\u9fff]+",
            text.casefold()
        ):

            if re.fullmatch(r"[\u4e00-\u9fff]+", part):

                if len(part) == 1:
                    tokens.append(part)

                else:
                    tokens.extend(
                        part[index:index + 2]
                        for index in range(len(part) - 1)
                    )

            else:
                tokens.append(part)

        return tokens

    @staticmethod
    def _chunk_pages(
        pages: list[tuple[int | None, str]]
    ) -> list[dict]:
        """将文本切分成可检索的片段。"""

        chunks = []

        index = 0

        for page_number, text in pages:

            normalized = re.sub(
                r"\n{3,}", "\n\n", text
            ).strip()

            if not normalized:
                continue

            start = 0

            while start < len(normalized):

                end = min(
                    len(normalized),
                    start + CHUNK_SIZE
                )

                if end < len(normalized):

                    split_at = normalized.rfind(
                        "\n",
                        start + CHUNK_SIZE // 2,
                        end
                    )

                    if split_at > start:
                        end = split_at

                content = normalized[start:end].strip()

                if len(content) >= 10:

                    chunks.append({
                        "chunk_index": index,
                        "page_start": page_number,
                        "page_end": page_number,
                        "content": content,
                    })

                    index += 1

                if end >= len(normalized):
                    break

                start = max(
                    start + 1,
                    end - CHUNK_OVERLAP
                )

                if index > 2000:
                    raise ValueError(
                        "文档切分后的片段过多，请拆分文档后再导入"
                    )

        return chunks

    @staticmethod
    def _extract(
        extension: str,
        content: bytes
    ) -> tuple[list[tuple[int | None, str]], int | None]:

        # PDF 文档
        if extension == ".pdf":

            try:
                from pypdf import PdfReader

                reader = PdfReader(BytesIO(content))

                if reader.is_encrypted:
                    try:
                        reader.decrypt("")
                    except Exception as exc:
                        raise ValueError(
                            "该 PDF 已加密，请解除密码保护后再导入"
                        ) from exc

                pages = [
                    (
                        index + 1,
                        page.extract_text() or ""
                    )
                    for index, page in enumerate(reader.pages)
                ]

                return pages, len(reader.pages)

            except ValueError:
                raise

            except Exception as exc:
                raise ValueError(
                    f"PDF 解析失败：{exc}"
                ) from exc

        # Word 文档
        if extension == ".docx":

            try:
                from docx import Document

                document = Document(BytesIO(content))

                parts = [
                    paragraph.text
                    for paragraph in document.paragraphs
                    if paragraph.text.strip()
                ]

                for table in document.tables:

                    for row in table.rows:

                        cells = [
                            cell.text.strip()
                            for cell in row.cells
                            if cell.text.strip()
                        ]

                        if cells:
                            parts.append(" | ".join(cells))

                return [
                    (None, "\n".join(parts))
                ], None

            except Exception as exc:
                raise ValueError(
                    f"Word 文档解析失败：{exc}"
                ) from exc

        # TXT / Markdown
        for encoding in (
            "utf-8-sig",
            "utf-8",
            "gb18030"
        ):

            try:
                return [
                    (None, content.decode(encoding))
                ], None

            except UnicodeDecodeError:
                continue

        raise ValueError(
            "文本文件编码无法识别，请转换为 UTF-8 后重新导入"
        )

    @staticmethod
    def _mime_type(extension: str) -> str:

        return {
            ".pdf": "application/pdf",
            ".docx": (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            ".txt": "text/plain; charset=utf-8",
            ".md": "text/markdown; charset=utf-8",
            ".markdown": "text/markdown; charset=utf-8",
        }.get(
            extension,
            "application/octet-stream"
        )
