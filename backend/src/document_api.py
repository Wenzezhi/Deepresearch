
"""本地文献管理 API。"""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from services.document_library import (
    MAX_UPLOAD_BYTES,
    DocumentLibrary,
    DuplicateDocumentError,
)


def router(library: DocumentLibrary):

    api = APIRouter(
        prefix="/documents",
        tags=["local-documents"]
    )

    # 获取文献列表
    @api.get("")
    def list_documents():
        return library.list_documents()

    # 上传文献
    @api.post("", status_code=201)
    async def upload_document(
        file: UploadFile = File(...)
    ):

        filename = file.filename or ""

        try:

            content = await file.read(
                MAX_UPLOAD_BYTES + 1
            )

            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    413,
                    "单个文件不能超过 25 MB"
                )

            return library.add_bytes(
                filename,
                content
            )

        except DuplicateDocumentError as exc:

            raise HTTPException(
                409,
                {
                    "message": str(exc),
                    "document": library.public_record(
                        exc.document
                    ),
                },
            ) from exc

        except ValueError as exc:

            raise HTTPException(
                400,
                str(exc)
            ) from exc

        finally:
            await file.close()

    # 下载原始文献
    @api.get("/{identifier}/download")
    def download_document(identifier: str):

        try:
            record = library.get_document(identifier)

        except KeyError as exc:
            raise HTTPException(
                404,
                str(exc)
            ) from exc

        path = Path(
            record.get("stored_path", "")
        )

        if (
            not path.is_file()
            or path.parent.resolve()
            != library.storage_dir.resolve()
        ):
            raise HTTPException(
                404,
                "原始文献文件不存在"
            )

        return FileResponse(
            path,
            media_type=record.get(
                "mime_type",
                "application/octet-stream"
            ),
            filename=record.get(
                "original_name",
                "document"
            ),
        )

    # 删除文献
    @api.delete("/{identifier}", status_code=204)
    def delete_document(identifier: str):

        try:
            library.delete_document(identifier)

        except KeyError as exc:
            raise HTTPException(
                404,
                str(exc)
            ) from exc

        except ValueError as exc:
            raise HTTPException(
                409,
                str(exc)
            ) from exc

        return None

    return api
