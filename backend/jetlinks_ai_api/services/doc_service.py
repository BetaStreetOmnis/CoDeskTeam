from __future__ import annotations

from ..config import Settings
from .docs import InspectionDocService, PptDocService, QuoteDocService


class DocService:
    """
    Facade for document generation.

    The concrete implementations are split by output type:
    - PptDocService: PPTX
    - QuoteDocService: quotation DOCX/XLSX
    - InspectionDocService: inspection DOCX/XLSX
    """

    def __init__(self, settings: Settings) -> None:
        self._ppt = PptDocService(settings)
        self._quote = QuoteDocService(settings)
        self._inspection = InspectionDocService(settings)

    async def create_pptx(
        self,
        *,
        title: str,
        slides: list[dict],
        style: str | None = None,
        layout_mode: str | None = None,
        template_file_id: str | None = None,
        template_mode: str | None = None,
        template_keep_images: bool | None = None,
        template_content_indices: list[int] | None = None,
    ) -> dict:
        return await self._ppt.create_pptx(
            title=title,
            slides=slides,
            style=style,
            layout_mode=layout_mode,
            template_file_id=template_file_id,
            template_mode=template_mode,
            template_keep_images=template_keep_images,
            template_content_indices=template_content_indices,
        )

    async def create_quote_docx(
        self,
        *,
        seller: str,
        buyer: str,
        currency: str,
        items: list[dict],
        note: str | None,
    ) -> dict:
        return await self._quote.create_quote_docx(
            seller=seller,
            buyer=buyer,
            currency=currency,
            items=items,
            note=note,
        )

    async def create_quote_xlsx(
        self,
        *,
        seller: str,
        buyer: str,
        currency: str,
        items: list[dict],
        note: str | None,
    ) -> dict:
        return await self._quote.create_quote_xlsx(
            seller=seller,
            buyer=buyer,
            currency=currency,
            items=items,
            note=note,
        )

    async def create_inspection_docx(
        self,
        *,
        title: str,
        basic_info: dict,
        device_info: dict,
        network_info: dict,
        inspection_info: dict,
        inspection_items: list[dict],
        conclusion: dict,
        signatures: dict,
        attachments: list[str] | None = None,
    ) -> dict:
        return await self._inspection.create_inspection_docx(
            title=title,
            basic_info=basic_info,
            device_info=device_info,
            network_info=network_info,
            inspection_info=inspection_info,
            inspection_items=inspection_items,
            conclusion=conclusion,
            signatures=signatures,
            attachments=attachments,
        )

    async def create_inspection_xlsx(
        self,
        *,
        title: str,
        basic_info: dict,
        device_info: dict,
        network_info: dict,
        inspection_info: dict,
        inspection_items: list[dict],
        conclusion: dict,
        signatures: dict,
        attachments: list[str] | None = None,
    ) -> dict:
        return await self._inspection.create_inspection_xlsx(
            title=title,
            basic_info=basic_info,
            device_info=device_info,
            network_info=network_info,
            inspection_info=inspection_info,
            inspection_items=inspection_items,
            conclusion=conclusion,
            signatures=signatures,
            attachments=attachments,
        )
