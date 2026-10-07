"""Bounded image uploads and data URLs for native multimodal LLM intake."""

import asyncio
import base64
import binascii
import shutil
import warnings
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import Settings, settings

IMAGE_FORMATS = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png"), "WEBP": ("image/webp", ".webp")}


class InvalidImageError(ValueError):
    pass


def image_format(data: bytes, config: Settings = settings) -> tuple[str, str]:
    if not data or len(data) > config.max_upload_size_mb * 1024 * 1024:
        raise InvalidImageError("Image is empty or exceeds the upload size limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in IMAGE_FORMATS:
                    raise InvalidImageError("Only JPEG, PNG, and WebP images are supported")
                if image.width * image.height > config.max_image_pixels:
                    raise InvalidImageError("Image exceeds the configured pixel limit")
                if getattr(image, "n_frames", 1) != 1:
                    raise InvalidImageError("Animated images are not supported")
                mime, suffix = IMAGE_FORMATS[image.format]
            # Frame inspection can move a plugin's file pointer; verification
            # must run on a freshly opened image.
            with Image.open(BytesIO(data)) as image:
                image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidImageError("Image cannot be decoded safely") from exc
    return mime, suffix


def image_data_url(data: bytes, config: Settings = settings) -> str:
    mime, _ = image_format(data, config)
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def normalize_base64_image(value: str, config: Settings = settings) -> tuple[str, int]:
    if not isinstance(value, str):
        raise InvalidImageError("Base64 image input must be a string")
    header = None
    encoded = value
    if value.startswith("data:"):
        header, separator, encoded = value.partition(",")
        if not separator or not header.endswith(";base64"):
            raise InvalidImageError("Image data URL must contain base64 content")
    limit = config.max_upload_size_mb * 1024 * 1024
    if len(encoded) > 4 * ((limit + 2) // 3):
        raise InvalidImageError("Encoded image exceeds the upload size limit")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidImageError("Invalid base64 image content") from exc
    mime, _ = image_format(data, config)
    if header is not None and header != f"data:{mime};base64":
        raise InvalidImageError("Image data URL MIME type does not match the file content")
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}", len(data)


class ImageService:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.root = Path(config.upload_dir).expanduser().resolve()

    def claim_directory(self, claim_id: str | UUID) -> Path:
        return self.root / str(UUID(str(claim_id)))

    async def save_uploads(self, claim_id: UUID, uploads: list[UploadFile]) -> list[str]:
        if len(uploads) > self.config.max_claim_images:
            raise InvalidImageError(f"At most {self.config.max_claim_images} images are allowed")
        if not uploads:
            return []
        directory = self.claim_directory(claim_id)
        await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=False)
        paths = []
        total = 0
        limit = self.config.max_upload_size_mb * 1024 * 1024
        try:
            for upload in uploads:
                chunks = []
                while chunk := await upload.read(64 * 1024):
                    total += len(chunk)
                    if total > limit:
                        raise InvalidImageError("Combined evidence images exceed the upload size limit")
                    chunks.append(chunk)
                data = b"".join(chunks)
                mime, suffix = await asyncio.to_thread(image_format, data, self.config)
                if upload.content_type not in (None, mime, "application/octet-stream"):
                    raise InvalidImageError("Uploaded image MIME type does not match its content")
                path = directory / f"{uuid4().hex}{suffix}"
                await asyncio.to_thread(path.write_bytes, data)
                paths.append(str(path))
            return paths
        except BaseException:
            await asyncio.to_thread(shutil.rmtree, directory, True)
            raise
        finally:
            for upload in uploads:
                await upload.close()

    def resolve_evidence(self, claim_id: UUID, stored_path: str) -> Path:
        path = Path(stored_path).resolve(strict=True)
        if not path.is_relative_to(self.claim_directory(claim_id)) or not path.is_file():
            raise InvalidImageError("Evidence path is outside this claim's upload directory")
        return path

    def cleanup(self, claim_id: UUID) -> None:
        directory = self.claim_directory(claim_id)
        if directory.is_dir():
            shutil.rmtree(directory)
