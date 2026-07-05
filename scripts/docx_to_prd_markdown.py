#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def q(name: str) -> str:
    prefix, local = name.split(":", 1)
    return f"{{{NS[prefix]}}}{local}"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def attr(el: ET.Element, name: str) -> str | None:
    return el.get(q(name))


def escape_markdown_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


class DocxMarkdownConverter:
    def __init__(self, source: Path, output: Path) -> None:
        self.source = source
        self.output = output
        self.output_dir = output.parent
        self.assets_dir = self.output_dir / "assets"
        self.media_written: dict[str, str] = {}
        self.list_counters: dict[tuple[str, str], int] = {}

    def convert(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

        with ZipFile(self.source) as archive:
            document = ET.fromstring(archive.read("word/document.xml"))
            style_names = self._style_names(archive)
            numbering = self._numbering(archive)
            relationships = self._relationships(archive)

            chunks: list[str] = []
            body = document.find("w:body", NS)
            if body is None:
                raise ValueError("DOCX document body not found")

            for child in list(body):
                kind = local_name(child.tag)
                if kind == "p":
                    paragraph = self._paragraph(child, style_names, numbering, relationships, archive)
                    if paragraph:
                        chunks.append(paragraph)
                elif kind == "tbl":
                    table = self._table(child, relationships, archive)
                    if table:
                        chunks.append(table)

            self.output.write_text("\n\n".join(chunks).rstrip() + "\n", encoding="utf-8")

    def _style_names(self, archive: ZipFile) -> dict[str, str]:
        styles_path = "word/styles.xml"
        if styles_path not in archive.namelist():
            return {}

        root = ET.fromstring(archive.read(styles_path))
        names: dict[str, str] = {}
        for style in root.findall(".//w:style", NS):
            style_id = attr(style, "w:styleId")
            name = style.find("w:name", NS)
            if style_id:
                names[style_id] = attr(name, "w:val") if name is not None else style_id
        return names

    def _relationships(self, archive: ZipFile) -> dict[str, str]:
        rels_path = "word/_rels/document.xml.rels"
        root = ET.fromstring(archive.read(rels_path))
        rels: dict[str, str] = {}
        for rel in root.findall("rel:Relationship", NS):
            rel_id = rel.get("Id")
            target = rel.get("Target")
            if rel_id and target:
                rels[rel_id] = target
        return rels

    def _numbering(self, archive: ZipFile) -> dict[str, dict[str, str]]:
        if "word/numbering.xml" not in archive.namelist():
            return {}

        root = ET.fromstring(archive.read("word/numbering.xml"))
        abstract_defs: dict[str, dict[str, str]] = {}
        for abstract in root.findall("w:abstractNum", NS):
            abstract_id = attr(abstract, "w:abstractNumId")
            if not abstract_id:
                continue
            levels: dict[str, str] = {}
            for level in abstract.findall("w:lvl", NS):
                ilvl = attr(level, "w:ilvl")
                num_fmt = level.find("w:numFmt", NS)
                if ilvl is not None and num_fmt is not None:
                    levels[ilvl] = attr(num_fmt, "w:val") or "decimal"
            abstract_defs[abstract_id] = levels

        numbering: dict[str, dict[str, str]] = {}
        for num in root.findall("w:num", NS):
            num_id = attr(num, "w:numId")
            abstract_ref = num.find("w:abstractNumId", NS)
            abstract_id = attr(abstract_ref, "w:val") if abstract_ref is not None else None
            if num_id and abstract_id:
                numbering[num_id] = abstract_defs.get(abstract_id, {})
        return numbering

    def _paragraph(
        self,
        paragraph: ET.Element,
        style_names: dict[str, str],
        numbering: dict[str, dict[str, str]],
        relationships: dict[str, str],
        archive: ZipFile,
    ) -> str:
        text = self._paragraph_text(paragraph).strip()
        images = self._images(paragraph, relationships, archive)

        pieces: list[str] = []
        if text:
            pieces.append(self._format_text_paragraph(paragraph, text, style_names, numbering))
        pieces.extend(images)
        return "\n\n".join(pieces)

    def _paragraph_text(self, element: ET.Element) -> str:
        parts: list[str] = []
        for node in element.iter():
            if node.tag == q("w:t"):
                parts.append(node.text or "")
            elif node.tag == q("w:tab"):
                parts.append("\t")
            elif node.tag in (q("w:br"), q("w:cr")):
                parts.append("\n")
        return "".join(parts)

    def _format_text_paragraph(
        self,
        paragraph: ET.Element,
        text: str,
        style_names: dict[str, str],
        numbering: dict[str, dict[str, str]],
    ) -> str:
        style_id_el = paragraph.find("./w:pPr/w:pStyle", NS)
        style_id = attr(style_id_el, "w:val") if style_id_el is not None else ""
        style_name = style_names.get(style_id or "", "")

        heading_level = {
            "MainTitle": 1,
            "heading 1": 2,
            "heading 2": 3,
            "heading 3": 4,
            "Title": 1,
            "Heading 1": 2,
            "Heading 2": 3,
            "Heading 3": 4,
        }.get(style_name)

        if heading_level:
            return f"{'#' * heading_level} {text}"

        num_id_el = paragraph.find("./w:pPr/w:numPr/w:numId", NS)
        ilvl_el = paragraph.find("./w:pPr/w:numPr/w:ilvl", NS)
        num_id = attr(num_id_el, "w:val") if num_id_el is not None else None
        ilvl = attr(ilvl_el, "w:val") if ilvl_el is not None else "0"

        if num_id:
            fmt = numbering.get(num_id, {}).get(ilvl, "decimal")
            indent = "  " * int(ilvl or "0")
            if fmt == "bullet":
                return f"{indent}- {text}"
            key = (num_id, ilvl)
            self.list_counters[key] = self.list_counters.get(key, 0) + 1
            return f"{indent}{self.list_counters[key]}. {text}"

        return text

    def _images(
        self,
        paragraph: ET.Element,
        relationships: dict[str, str],
        archive: ZipFile,
    ) -> list[str]:
        output: list[str] = []
        for blip in paragraph.findall(".//a:blip", NS):
            rel_id = attr(blip, "r:embed")
            target = relationships.get(rel_id or "")
            if not target:
                continue

            media_path = f"word/{target}" if not target.startswith("word/") else target
            media_path = media_path.replace("word/../", "")
            filename = Path(media_path).name
            if media_path not in self.media_written:
                destination = self.assets_dir / filename
                with archive.open(media_path) as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                self.media_written[media_path] = f"assets/{filename}"
            output.append(f"![文档图片](%s)" % self.media_written[media_path])
        return output

    def _cell_markdown(self, cell: ET.Element, relationships: dict[str, str], archive: ZipFile) -> str:
        paragraphs: list[str] = []
        for paragraph in cell.findall("./w:p", NS):
            parts: list[str] = []
            text = self._paragraph_text(paragraph).strip()
            if text:
                parts.append(text)
            parts.extend(self._images(paragraph, relationships, archive))
            if parts:
                paragraphs.append(" ".join(parts))
        return escape_markdown_table_cell("\n".join(paragraphs))

    def _table(self, table: ET.Element, relationships: dict[str, str], archive: ZipFile) -> str:
        rows: list[list[str]] = []
        for row in table.findall("./w:tr", NS):
            cells = [
                self._cell_markdown(cell, relationships, archive)
                for cell in row.findall("./w:tc", NS)
            ]
            if cells:
                rows.append(cells)

        if not rows:
            return ""

        width = max(len(row) for row in rows)
        normalized = [row + [""] * (width - len(row)) for row in rows]
        header = "| " + " | ".join(normalized[0]) + " |"
        divider = "| " + " | ".join(["---"] * width) + " |"
        body = ["| " + " | ".join(row) + " |" for row in normalized[1:]]
        return "\n".join([header, divider, *body])


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: docx_to_prd_markdown.py SOURCE.docx OUTPUT.md", file=sys.stderr)
        return 2

    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    DocxMarkdownConverter(source, output).convert()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
