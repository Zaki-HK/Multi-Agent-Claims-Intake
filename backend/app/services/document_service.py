"""Local policy PDF conversion with Docling; retain structure and provenance."""

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from app.config import Settings, settings

if TYPE_CHECKING:
    from docling_core.types.doc import DoclingDocument


class DocumentParsingError(ValueError):
    """A policy could not be converted completely into usable Markdown."""


@dataclass(frozen=True)
class ParsedDocument:
    source_path: Path
    markdown: str
    page_count: int
    document: "DoclingDocument"


class DocumentService:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self._converter = None
        self._lock = Lock()

    def _get_converter(self):
        # Loading this module does not download models or allocate their memory.
        if self._converter is None:
            from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            options = PdfPipelineOptions()
            options.accelerator_options = AcceleratorOptions(
                device=AcceleratorDevice.CPU, num_threads=self.config.docling_num_threads
            )
            options.do_ocr = self.config.docling_enable_ocr
            options.do_table_structure = True
            options.table_structure_options.do_cell_matching = True
            self._converter = DocumentConverter(
                allowed_formats=[InputFormat.PDF],
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
            )
        return self._converter

    def parse_pdf(self, source: str | Path) -> ParsedDocument:
        path = Path(source).expanduser().resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise DocumentParsingError("Policy source must be a local PDF file")
        max_bytes = self.config.max_upload_size_mb * 1024 * 1024
        if not 0 < path.stat().st_size <= max_bytes:
            raise DocumentParsingError(
                f"PDF must be nonempty and no larger than {self.config.max_upload_size_mb} MB"
            )
        with path.open("rb") as stream:
            if b"%PDF-" not in stream.read(1024):
                raise DocumentParsingError("File does not contain a PDF header")

        from docling.datamodel.base_models import ConversionStatus

        try:
            with self._lock:
                result = self._get_converter().convert(
                    path, max_file_size=max_bytes, max_num_pages=self.config.docling_max_pages
                )
                # Partial output could silently omit exclusions or coverage limits.
                if result.status != ConversionStatus.SUCCESS:
                    raise DocumentParsingError(f"Docling conversion did not complete: {result.status}")
                document = result.document
                markdown = document.export_to_markdown().strip()
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"Docling could not parse {path.name}") from exc
        if not markdown or not document.pages:
            raise DocumentParsingError("PDF conversion produced no usable content or pages")
        return ParsedDocument(path, markdown, len(document.pages), document)

    def pdf_to_markdown(self, source: str | Path) -> str:
        return self.parse_pdf(source).markdown

    async def aparse_pdf(self, source: str | Path) -> ParsedDocument:
        return await asyncio.to_thread(self.parse_pdf, source)


@lru_cache(maxsize=1)
def get_document_service() -> DocumentService:
    return DocumentService()
