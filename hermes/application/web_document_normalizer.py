import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, Tuple
from bs4 import BeautifulSoup, Tag, NavigableString


@dataclass(frozen=True)
class NormalizationResult:
    title: str
    markdown: str
    metadata: Dict[str, str]
    content_hash: str
    warnings: Tuple[str, ...]
    dynamic_fallback_recommended: bool


class WebDocumentNormalizer:
    def __init__(self):
        pass

    def normalize(self, html: str, base_url: str = "", max_markdown_chars: int = 200_000) -> NormalizationResult:
        warnings = []
        if not html:
            empty_hash = hashlib.sha256(b"").hexdigest()
            return NormalizationResult(
                title="",
                markdown="",
                metadata={},
                content_hash=empty_hash,
                warnings=("empty_html",),
                dynamic_fallback_recommended=True,
            )

        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        if not title:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()
        if not title:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text().strip()

        # Extract metadata
        metadata: Dict[str, str] = {}
        meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
        if meta_desc and meta_desc.get("content"):
            metadata["description"] = meta_desc["content"].strip()

        meta_author = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", property="og:article:author")
        if meta_author and meta_author.get("content"):
            metadata["author"] = meta_author["content"].strip()

        meta_pub = soup.find("meta", property="article:published_time") or soup.find("meta", attrs={"name": "publication_date"})
        if meta_pub and meta_pub.get("content"):
            metadata["published_time"] = meta_pub["content"].strip()

        meta_site = soup.find("meta", property="og:site_name")
        if meta_site and meta_site.get("content"):
            metadata["site_name"] = meta_site["content"].strip()

        link_canon = soup.find("link", rel="canonical") or soup.find("meta", property="og:url")
        if link_canon and link_canon.get("href"):
            metadata["canonical_url"] = link_canon["href"].strip()
        elif link_canon and link_canon.get("content"):
            metadata["canonical_url"] = link_canon["content"].strip()

        # Detect script count before removing
        script_count = len(soup.find_all("script"))

        # Remove unwanted tags & elements
        unwanted_tags = ["script", "style", "nav", "footer", "form", "noscript", "svg", "canvas", "iframe"]
        for tag_name in unwanted_tags:
            for element in soup.find_all(tag_name):
                element.decompose()

        # Remove elements with hidden styles/attributes
        for element in soup.find_all(True):
            style = (element.get("style") or "").lower()
            aria_hidden = (element.get("aria-hidden") or "").lower()
            if "display:none" in style.replace(" ", "") or "visibility:hidden" in style.replace(" ", "") or aria_hidden == "true":
                element.decompose()

        # Locate target container
        target_container = soup.find("main") or soup.find("article") or soup.body or soup

        # Convert to markdown text
        markdown_text = self._convert_node_to_markdown(target_container)
        markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text).strip()

        # Truncate if exceeds max_markdown_chars
        if len(markdown_text) > max_markdown_chars:
            markdown_text = markdown_text[:max_markdown_chars]
            warnings.append("markdown_truncated")

        content_hash = hashlib.sha256(markdown_text.encode("utf-8")).hexdigest()

        # Evaluate dynamic fallback recommendation
        lowered_text = markdown_text.lower()
        has_main_or_article = soup.find("main") is not None or soup.find("article") is not None
        
        dynamic_fallback = False
        if len(markdown_text) < 300:
            dynamic_fallback = True
        elif any(indicator in lowered_text for indicator in ["loading...", "please enable javascript", "javascript is required", "enable js"]):
            dynamic_fallback = True
        elif script_count >= 3 and not has_main_or_article and len(markdown_text) < 500:
            dynamic_fallback = True

        if dynamic_fallback and "dynamic_content_not_rendered" not in warnings:
            warnings.append("dynamic_content_not_rendered")

        return NormalizationResult(
            title=title,
            markdown=markdown_text,
            metadata=metadata,
            content_hash=content_hash,
            warnings=tuple(warnings),
            dynamic_fallback_recommended=dynamic_fallback,
        )

    def _convert_node_to_markdown(self, node) -> str:
        if isinstance(node, NavigableString):
            return str(node)

        if not isinstance(node, Tag):
            return ""

        tag_name = node.name.lower()

        if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(tag_name[1])
            text = "".join(self._convert_node_to_markdown(child) for child in node.children).strip()
            return f"\n\n{'#' * level} {text}\n\n"

        if tag_name == "p":
            text = "".join(self._convert_node_to_markdown(child) for child in node.children).strip()
            return f"\n\n{text}\n\n" if text else ""

        if tag_name in ["ul", "ol"]:
            items = []
            for child in node.children:
                if isinstance(child, Tag) and child.name.lower() == "li":
                    item_text = "".join(self._convert_node_to_markdown(c) for c in child.children).strip()
                    if item_text:
                        items.append(f"* {item_text}")
            return "\n\n" + "\n".join(items) + "\n\n" if items else ""

        if tag_name == "a":
            href = node.get("href", "").strip()
            text = "".join(self._convert_node_to_markdown(child) for child in node.children).strip()
            if not text:
                return ""
            if href and not href.startswith("javascript:") and not href.startswith("data:"):
                return f"[{text}]({href})"
            return text

        if tag_name in ["code", "pre"]:
            text = node.get_text().strip()
            if tag_name == "pre" or "\n" in text:
                return f"\n\n```\n{text}\n```\n\n"
            return f"`{text}`"

        if tag_name == "blockquote":
            text = "".join(self._convert_node_to_markdown(child) for child in node.children).strip()
            lines = [f"> {line}" for line in text.splitlines() if line.strip()]
            return "\n\n" + "\n".join(lines) + "\n\n" if lines else ""

        if tag_name == "img":
            alt = node.get("alt", "").strip()
            return f"![{alt}]" if alt else ""

        # Default block / inline container handling
        child_texts = [self._convert_node_to_markdown(child) for child in node.children]
        res = "".join(child_texts)
        if tag_name in ["div", "section", "article", "header", "table", "tr", "td", "th"]:
            return f"\n{res}\n"
        return res
