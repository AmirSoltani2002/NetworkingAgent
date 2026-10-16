import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import IngestionError


@dataclass
class Section:
    content: str
    heading: str | None
    path: str | None
    page: int | None
    protected: bool = False
    warning_page: int | None = None


@dataclass
class Chunk:
    content: str
    heading: str | None
    path: str | None
    page: int | None
    metadata: dict = field(default_factory=dict)


def extract(path: Path, settings):
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(str(path), strict=True)
            if reader.is_encrypted:
                raise IngestionError("Encrypted PDFs are not supported")
            if len(reader.pages) > settings.max_pdf_pages:
                raise IngestionError("PDF exceeds the configured page limit")
            pages = []
            total = 0
            for number, page in enumerate(reader.pages, 1):
                content = page.extract_text(extraction_mode="layout") or ""
                total += len(content)
                if total > settings.max_extract_chars:
                    raise IngestionError("Extracted text exceeds the configured limit")
                pages.append((number, content))
        except IngestionError:
            raise
        except Exception:
            raise IngestionError("PDF extraction failed; the file may be corrupt or unsupported") from None
    elif path.suffix.lower() in {".txt", ".md", ".markdown"}:
        try:
            content = path.read_text(encoding="utf-8-sig")
        except (UnicodeError, OSError):
            raise IngestionError("Text extraction failed; use a readable UTF-8 document") from None
        if len(content) > settings.max_extract_chars:
            raise IngestionError("Extracted text exceeds the configured limit")
        pages = [(None, content)]
    else:
        raise IngestionError("Unsupported document format")
    if not any(content.strip() for _, content in pages):
        raise IngestionError("No extractable text found; scanned PDFs require external OCR before upload")
    return pages


def structures(pages):
    sections = []
    stack = []
    lines = []
    page_start = None
    carry_warning = ""
    carry_page = None
    warning_page = None

    def flush():
        content = "\n".join(lines).strip()
        if content:
            protected = bool(
                re.search(
                    r"(?im)^\s*(?:warning|caution|danger|safety|symptom|cause|solution|resolution|"
                    r"diagnostic|procedure|\d+[.)]\s)",
                    content,
                )
            )
            sections.append(
                Section(
                    content,
                    stack[-1][1] if stack else None,
                    " / ".join(title for _, title in stack) or None,
                    page_start,
                    protected,
                    warning_page,
                )
            )
        lines.clear()

    # Preserve exact page provenance. Carry a warning into a continued procedure on the next page.
    for number, content in pages:
        warning_page = None
        page_start = number
        for line in content.splitlines():
            heading = re.match(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$", line)
            plain = line.strip()
            if not heading and plain and len(plain) <= 100 and len(plain.split()) <= 12:
                if (plain.isupper() and any(character.isalpha() for character in plain)) or plain.endswith(
                    ":"
                ):
                    heading = (1, plain.rstrip(":"))
            if heading:
                flush()
                carry_warning = ""
                carry_page = None
                level, title = (
                    (len(heading.group(1)), heading.group(2)) if hasattr(heading, "group") else heading
                )
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title.strip()))
                page_start = number
            if not lines:
                page_start = number
                if carry_warning and not heading and line.strip():
                    lines.append(carry_warning)
                    warning_page = carry_page
            lines.append(line)
            if re.match(r"\s*(WARNING|CAUTION|DANGER|SAFETY)\b", line, re.IGNORECASE):
                carry_warning = line
                carry_page = number
        flush()
    return sections


class Chunker:
    def __init__(self, settings, embeddings):
        self.settings = settings
        self.embeddings = embeddings
        self._semantic = None

    def semantic(self, section):
        from llama_index.core import Document as LlamaDocument
        from llama_index.core.node_parser import SemanticSplitterNodeParser

        if self._semantic is None:
            self._semantic = SemanticSplitterNodeParser(
                embed_model=self.embeddings.llama_model,
                buffer_size=self.settings.semantic_buffer_size,
                breakpoint_percentile_threshold=self.settings.semantic_breakpoint_percentile,
                include_metadata=False,
            )
        return [
            node.text
            for node in self._semantic.get_nodes_from_documents([LlamaDocument(text=section.content)])
        ]

    def bounded(self, text, protected):
        if self.embeddings.token_count(text) <= self.embeddings.max_tokens:
            return [(text, False)]
        # Pack paragraph/step blocks first. Repeat safety warnings if a long procedure must split.
        blocks = re.split(r"\n\s*\n", text)
        warning = "\n".join(
            line
            for line in text.splitlines()
            if re.match(r"\s*(WARNING|CAUTION|DANGER|SAFETY)\b", line, re.IGNORECASE)
        )
        result = []
        current = ""
        for block in blocks:
            combined = (current + "\n\n" + block).strip()
            if self.embeddings.token_count(combined) <= self.embeddings.max_tokens:
                current = combined
                continue
            if current:
                result.append(current)
                current = ""
            if self.embeddings.token_count(block) <= self.embeddings.max_tokens:
                current = block
            else:
                # Oversized individual blocks get token-bounded fragments, retaining a safety prefix.
                result.extend(self.embeddings.token_parts(block))
        if current:
            result.append(current)
        bounded = []
        for part in result:
            if protected and warning and warning not in part:
                budget = self.embeddings.max_tokens - self.embeddings.token_count(warning) - 2
                if budget < 16:
                    raise IngestionError(
                        "Safety warning exceeds the chunk token budget; increase the limit or restructure the source"
                    )
                for fragment in self.embeddings.token_parts(part, budget):
                    bounded.append((warning + "\n" + fragment, True))
            else:
                for fragment in self.embeddings.token_parts(part):
                    bounded.append((fragment, True))
        return bounded

    def split(self, sections):
        chunks = []
        for section in sections:
            if not section.protected and len(section.content) >= self.settings.semantic_min_chars:
                passages = self.semantic(section)
                method = "semantic_within_section"
            else:
                passages = [section.content]
                method = "protected_structure" if section.protected else "structure"
            for passage in passages:
                for content, forced in self.bounded(passage.strip(), section.protected):
                    if content.strip():
                        chunks.append(
                            Chunk(
                                content.strip(),
                                section.heading,
                                section.path,
                                section.page,
                                {
                                    "chunking_method": method,
                                    "forced_token_split": forced,
                                    "protected_procedure": section.protected,
                                },
                            )
                        )
                        if section.page is not None:
                            chunks[-1].metadata["page_numbers"] = sorted(
                                {
                                    number
                                    for number in [section.page, section.warning_page]
                                    if number is not None
                                }
                            )
        if not chunks:
            raise IngestionError("No searchable passages could be extracted")
        if len(chunks) > self.settings.max_chunks:
            raise IngestionError("Document exceeds the configured chunk limit")
        return chunks
