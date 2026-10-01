import os
import uuid
from typing import List

import pytesseract
from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError

from parsers.base import BaseParser, Chunk, ParseError

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg"}
NO_TEXT_PLACEHOLDER = "[Image: no readable text detected]"
MIN_DIMENSION = 300


class ImageParser(BaseParser):
    def parse(self, file_path: str) -> List[Chunk]:
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ParseError(f"Unsupported image type: {file_path}")
        if not os.path.isfile(file_path):
            raise ParseError(f"Image not found: {file_path}")

        try:
            with Image.open(file_path) as raw:
                img = self._preprocess(raw)
        except (UnidentifiedImageError, OSError) as e:
            raise ParseError(f"Failed to open image: {file_path}") from e

        try:
            text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")
        except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError) as e:
            raise ParseError(f"OCR failed for image: {file_path}") from e

        if not text or not text.strip():
            return [self._placeholder_chunk()]

        return self._chunk(text.strip())

    def _preprocess(self, raw: Image.Image) -> Image.Image:
        img = ImageOps.exif_transpose(raw)

        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))
            img = background
        else:
            img = img.convert("RGB")

        img = ImageEnhance.Sharpness(img).enhance(2.0)

        width, height = img.size
        if width < MIN_DIMENSION or height < MIN_DIMENSION:
            img = img.resize((width * 2, height * 2), Image.LANCZOS)

        return img

    def _placeholder_chunk(self) -> Chunk:
        return Chunk(
            id=str(uuid.uuid4()),
            content=NO_TEXT_PLACEHOLDER,
            token_count=0,
            chunk_index=0,
            start_char=0,
            end_char=len(NO_TEXT_PLACEHOLDER),
            page_number=None,
        )


def parse_image(file_path: str) -> List[Chunk]:
    return ImageParser().parse(file_path)
