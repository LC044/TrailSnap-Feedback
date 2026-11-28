"""Bounded, in-memory attachments for the stateless AI assistant."""
import base64
import binascii
from pathlib import PurePosixPath
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

TEXT_SUFFIXES = {".txt", ".log", ".md", ".csv", ".json", ".xml", ".yaml", ".yml"}
MAX_IMAGES = 5
MAX_FILES = 3
MAX_IMAGE_BYTES = 36000
MAX_TEXT_BYTES = 6000


class IntakeAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    kind: Literal["image", "text"]
    name: str = Field(min_length=1, max_length=140)
    data: str = Field(min_length=1, max_length=48000)


def bounded_jpeg(raw: bytes) -> bool:
    # Read only the SOF dimensions; do not decode or allocate pixels on the server.
    if not (raw.startswith(b"\xff\xd8\xff") and raw.endswith(b"\xff\xd9")):
        return False
    offset = 2
    while offset + 4 <= len(raw) - 2 and raw[offset] == 255:
        while offset < len(raw) and raw[offset] == 255:
            offset += 1
        if offset + 3 > len(raw) - 2:
            return False
        marker = raw[offset]
        length = int.from_bytes(raw[offset + 1:offset + 3], "big")
        if length < 2 or offset + 1 + length > len(raw) - 2 or marker in {0xDA, 0xD9}:
            return False
        if marker in {0xC0, 0xC1, 0xC2} and length >= 8:
            height = int.from_bytes(raw[offset + 4:offset + 6], "big")
            width = int.from_bytes(raw[offset + 6:offset + 8], "big")
            return 1 <= height <= 1200 and 1 <= width <= 1200
        offset += 1 + length
    return False


def prepare_attachments(items):
    texts, images = [], []
    text_bytes = 0
    for item in items:
        name = PurePosixPath(item.name.replace("\\", "/")).name
        if not name or any(ord(char) < 32 for char in name):
            raise HTTPException(422, "附件文件名无效")
        try:
            raw = base64.b64decode(item.data, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(422, "附件编码无效，请重新选择文件") from None
        if item.kind == "image":
            if len(images) >= MAX_IMAGES:
                raise HTTPException(422, "每条消息最多上传 5 张照片")
            if len(raw) > MAX_IMAGE_BYTES or not bounded_jpeg(raw):
                raise HTTPException(422, "图片格式或尺寸不符合要求，请重新选择照片")
            images.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": item.data}})
        else:
            if len(texts) >= MAX_FILES:
                raise HTTPException(422, "每条消息最多上传 3 个文本文件")
            if PurePosixPath(name).suffix.lower() not in TEXT_SUFFIXES:
                raise HTTPException(422, "仅支持 TXT、LOG、Markdown、CSV、JSON、XML 和 YAML 文本文件")
            text_bytes += len(raw)
            if text_bytes > MAX_TEXT_BYTES:
                raise HTTPException(422, "文本附件合计不能超过 6 KB，请截取相关内容")
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise HTTPException(422, "文本附件须使用 UTF-8 编码") from None
            if not text.strip() or any(ord(char) < 32 and char not in "\n\r\t" for char in text):
                raise HTTPException(422, "附件不包含可读取的文本")
            texts.append({"name": name, "content": text})
    return texts, images
