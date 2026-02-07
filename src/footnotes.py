import re
from typing import Callable, Dict, List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag

from .config import MAX_FOOTNOTE_LENGTH, MIN_FOOTNOTE_TEXT_LENGTH
from .utils import clean_text_fragments


def extract_footnotes(soup: BeautifulSoup) -> Dict[str, str]:
    footnotes: Dict[str, str] = {}

    footnotes_heading = soup.find(string=re.compile(r"^(Footnotes?|Notes?)$", re.I))
    if footnotes_heading:
        heading_elem = footnotes_heading.find_parent()
        if heading_elem:
            for elem in heading_elem.find_all_next(["p", "li"]):
                parent_heading = elem.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
                if parent_heading and parent_heading is not heading_elem:
                    heading_text = parent_heading.get_text(strip=True).lower()
                    if heading_text and "footnote" not in heading_text and "note" not in heading_text:
                        break

                text = elem.get_text(strip=True)
                if not text or len(text) < MIN_FOOTNOTE_TEXT_LENGTH:
                    continue

                if re.match(r"^(MIA|Archive).*>(Archive|.*>.*)", text, re.I):
                    continue

                footnote_match = re.match(r"^(\*+)?\s*\[?(\d+)\]?\.?\s*(.+)$", text, re.S)
                if not footnote_match:
                    footnote_match = re.match(r"^\[(\d+)\]\s*(.+)$", text, re.S)

                if footnote_match:
                    footnote_num = footnote_match.group(2)
                    footnote_text = footnote_match.group(3)

                    footnote_text = re.sub(r"^\*+\s*", "", footnote_text)
                    footnote_text = clean_text_fragments(footnote_text)

                    if footnote_text and len(footnote_text) < MAX_FOOTNOTE_LENGTH:
                        anchors = elem.find_all("a", attrs={"name": True}) + elem.find_all("a", attrs={"id": True})

                        effective_anchor_count = 0
                        temp_contents = list(elem.children)
                        temp_contents_set = set(temp_contents)
                        for a in anchors:
                            if a in temp_contents_set:
                                effective_anchor_count += 1

                        if effective_anchor_count <= 1:
                            raw = elem.get_text("\n", strip=True)
                            parts = list(re.finditer(r"(?m)^(\d+)\.\s*", raw))
                            if len(parts) > 1:
                                for idx, match in enumerate(parts):
                                    num_val = match.group(1)
                                    start = match.end()
                                    end = parts[idx + 1].start() if idx + 1 < len(parts) else len(raw)
                                    segment = raw[start:end].strip()
                                    segment = clean_text_fragments(segment)
                                    if segment:
                                        num_key = f"n{num_val}".lower()
                                        direct_key = num_val
                                        if num_key not in footnotes:
                                            footnotes[num_key] = segment
                                        if direct_key not in footnotes:
                                            footnotes[direct_key] = segment
                                elem.decompose()
                                continue

                        anchor_specific_text: Dict[str, str] = {}
                        if effective_anchor_count > 1:
                            contents = list(elem.children)
                            anchor_positions: List[int] = []
                            anchors_in_contents: List[Tag] = []
                            for anchor in anchors:
                                try:
                                    idx = contents.index(anchor)
                                except ValueError:
                                    continue
                                anchor_positions.append(idx)
                                anchors_in_contents.append(anchor)

                            for i, anchor in enumerate(anchors_in_contents):
                                start = anchor_positions[i]
                                end = anchor_positions[i + 1] if i + 1 < len(anchor_positions) else len(contents)
                                if start >= len(contents) or end > len(contents) or start >= end:
                                    continue
                                segment_parts: List[str] = []
                                for part in contents[start + 1 : end]:
                                    if isinstance(part, Tag):
                                        if part.name == "br":
                                            segment_parts.append("\n")
                                            continue
                                        segment_parts.append(part.get_text(" ", strip=True))
                                    elif isinstance(part, NavigableString):
                                        segment_parts.append(str(part))
                                segment_text = clean_text_fragments(" ".join(segment_parts))
                                segment_text = re.sub(r"^\[?\d+\]?\.?\s*", "", segment_text).strip()
                                if segment_text and len(segment_text) < MAX_FOOTNOTE_LENGTH:
                                    anchor_specific_text[id(anchor)] = segment_text

                        for anchor in anchors:
                            anchor_id = anchor.get("name") or anchor.get("id")
                            if not anchor_id:
                                continue
                            anchor_key = anchor_id.lower()

                            specific = anchor_specific_text.get(id(anchor), footnote_text)
                            if specific:
                                footnotes[anchor_key] = specific

                                anchor_num = re.search(r"(\d+)", anchor_key)
                                num_val = anchor_num.group(1) if anchor_num else footnote_num
                                if num_val:
                                    num_key = f"n{num_val}".lower()
                                    direct_key = num_val
                                    if num_key not in footnotes:
                                        footnotes[num_key] = specific
                                    if direct_key not in footnotes:
                                        footnotes[direct_key] = specific

                        elem.decompose()

    for node in soup.find_all(["p", "div"], class_=re.compile(r"(endnote|footnote)", re.I)):
        anchor = node.find("a", attrs={"name": True}) or node.find("a", attrs={"id": True})
        if not anchor:
            continue

        text_content = node.get_text(strip=True)
        if re.match(r"^\[?\d+\]?$", text_content):
            continue

        anchor_text = anchor.get_text(strip=True)
        if re.match(r"^\[?\d+\]?$", anchor_text):
            if len(text_content) < 50:
                continue

        anchor_id = anchor.get("name") or anchor.get("id")
        if anchor_id:
            key = anchor_id.lower()
            if key in footnotes:
                node.decompose()
                continue

            if not anchor.get_text(strip=True):
                anchor.decompose()

            content = clean_text_fragments(node.get_text(" ", strip=True))
            content = re.sub(r"^\[?\d+\]?\s*", "", content)

            if content and len(content) < 50000:
                footnotes[key] = content
                node.decompose()

    seen = set()
    anchors = []
    for a in soup.find_all("a", attrs={"name": True}) + soup.find_all("a", attrs={"id": True}):
        if a not in seen:
            seen.add(a)
            anchors.append(a)

    for anchor in anchors:
        if not anchor or not hasattr(anchor, "get"):
            continue
        if getattr(anchor, "attrs", None) is None:
            continue

        anchor_id = anchor.get("name") or anchor.get("id")
        if not anchor_id:
            continue

        if anchor_id.lower() in footnotes:
            continue

        key = anchor_id.lower()

        parent = anchor.find_parent(["p", "li", "div"])
        target = parent if parent else anchor

        if parent:
            parent_text = parent.get_text(strip=True)
        else:
            parent_text = anchor.get_text(strip=True)

        anchor_text = anchor.get_text(strip=True)

        if not anchor_text:
            continue

        if not parent_text.startswith(anchor_text):
            if not parent_text.startswith("[" + anchor_text) and not parent_text.startswith(anchor_text.replace("[", "").replace("]", "")):
                continue

        if re.match(r"^\[?\d+\]?$", parent_text):
            continue

        clean_text = clean_text_fragments(target.get_text(" ", strip=True))
        clean_text = re.sub(r"^\s*\[?\d+\]?[\.\)]?\s*", "", clean_text)

        if re.match(r"^(MIA|Archive).*>(Archive|.*>.*)", clean_text, re.I):
            continue

        if clean_text and len(clean_text) > 5 and len(clean_text) < MAX_FOOTNOTE_LENGTH:
            footnotes[key] = clean_text
            target.decompose()

    footnotes_heading = soup.find(string=re.compile(r"^(Footnotes?|Notes?)$", re.I))
    if footnotes_heading:
        heading_elem = footnotes_heading.find_parent()
        if heading_elem:
            for elem in heading_elem.find_all_next(["p", "li"], limit=50):
                parent_heading = elem.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
                if parent_heading and parent_heading is not heading_elem:
                    heading_text = parent_heading.get_text(strip=True).lower()
                    if heading_text and "footnote" not in heading_text and "note" not in heading_text:
                        break

                text = elem.get_text(strip=True)
                if not text or len(text) < MIN_FOOTNOTE_TEXT_LENGTH:
                    continue

                bracket_match = re.match(r"^\[(\d+)\]\s*(.+)$", text, re.S)
                if bracket_match:
                    num = bracket_match.group(1)
                    content = clean_text_fragments(bracket_match.group(2))
                    if content and len(content) < MAX_FOOTNOTE_LENGTH:
                        for key_variant in [num, f"n{num}", f"note{num}", f"footnote{num}"]:
                            if key_variant.lower() not in footnotes:
                                footnotes[key_variant.lower()] = content

    if footnotes_heading:
        heading_elem = footnotes_heading.find_parent()
        if heading_elem:
            for table in heading_elem.find_all_next("table", limit=50):
                parent_heading = table.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
                if parent_heading and parent_heading is not heading_elem:
                    heading_text = parent_heading.get_text(strip=True).lower()
                    if heading_text and "footnote" not in heading_text and "note" not in heading_text:
                        break

                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    if len(cells) >= 2:
                        anchor_cell = cells[0]
                        content_cell = cells[1]

                        anchor = anchor_cell.find("a", attrs={"id": True}) or anchor_cell.find("a", attrs={"name": True})
                        if anchor:
                            anchor_id = anchor.get("id") or anchor.get("name")
                            if anchor_id:
                                content_text = clean_text_fragments(content_cell.get_text("\n", strip=True))
                                content_text = re.sub(r"^\[?\d+\]?\.?\s*", "", content_text).strip()

                                if content_text and len(content_text) < MAX_FOOTNOTE_LENGTH:
                                    key = anchor_id.lower()
                                    if key not in footnotes:
                                        footnotes[key] = content_text
                                    num_match = re.search(r"(\d+)", key)
                                    if num_match:
                                        num = num_match.group(1)
                                        for variant in [num, f"n{num}", f"note{num}", f"footnote{num}"]:
                                            if variant not in footnotes:
                                                footnotes[variant] = content_text

    normalized: Dict[str, str] = {}
    for key, text in footnotes.items():
        k = key.lower()
        normalized.setdefault(k, text)
        num_match = re.search(r"(\d+)", k)
        if num_match:
            num = num_match.group(1)
            for alt in (num, f"n{num}", f"note{num}", f"footnote{num}", f"fn{num}"):
                normalized.setdefault(alt, text)
        for prefix in ("fw", "bk"):
            if k.startswith(prefix):
                stripped = k[len(prefix):]
                if stripped:
                    normalized.setdefault(stripped, text)

    return normalized


def match_footnote_content(ref: Tag, footnotes: Dict[str, str]) -> Optional[str]:
    href = ref.get("href", "")
    link_text = ref.get_text(" ", strip=True)
    href_lower = href.lower()

    if href_lower in ("#top", "#toc"):
        return None

    if href_lower.startswith("#s") or href_lower.startswith("#fig"):
        return None

    if re.match(r"^(MIA|Archive).*>(Archive|.*>.*)", link_text, re.I):
        return None

    candidates: List[str] = []

    if href.startswith("#"):
        raw = href.lstrip("#").lower()
        candidates.append(raw)
        for prefix in ("fw", "bk"):
            if raw.startswith(prefix):
                candidates.append(raw[len(prefix):])
        num_match = re.search(r"(\d+)", raw)
        if num_match:
            num = num_match.group(1)
            candidates.extend([num, f"n{num}", f"note{num}", f"footnote{num}"])

    text_num = re.search(r"(\d+)", link_text)
    if text_num:
        num = text_num.group(1)
        candidates.extend([num, f"n{num}", f"note{num}", f"footnote{num}"])

    seen: set[str] = set()
    ordered_candidates = []
    for cand in candidates:
        if cand and cand not in seen:
            seen.add(cand)
            ordered_candidates.append(cand)

    for cand in ordered_candidates:
        if cand in footnotes:
            return footnotes[cand]
    return None


def inline_footnote_refs(soup: BeautifulSoup, footnotes: Dict[str, str], log_fn: Callable[[str], None]) -> Dict[str, int]:
    unmatched_examples: List[str] = []
    matched = 0
    unmatched = 0
    for ref in soup.find_all("a", href=True):
        href = ref["href"]
        if not href.startswith("#"):
            continue

        content = match_footnote_content(ref, footnotes)

        if content:
            placeholder = soup.new_tag("latexfootnote")
            placeholder["content"] = content
            ref.replace_with(placeholder)
            matched += 1
        else:
            unmatched += 1
            if len(unmatched_examples) < 5 and not href.lower().startswith("#s"):
                text_preview = ref.get_text(" ", strip=True)[:40]
                unmatched_examples.append(f"{href} ({text_preview})")
            ref.unwrap()

    if unmatched_examples:
        sample = "; ".join(unmatched_examples)
        log_fn(f"Warning: {len(unmatched_examples)} footnote references had no match: {sample}")

    return {
        "inlined": matched,
        "unmatched_refs": unmatched,
    }


def inline_manual_footnote_refs(
    soup: BeautifulSoup,
    content_node: Tag,
    footnotes: Dict[str, str],
    log_fn: Callable[[str], None],
) -> int:
    footnote_pattern = re.compile(r"\[(\d+)\]")

    manual_matched = 0
    manual_unmatched: List[str] = []

    if not content_node:
        return 0

    text_nodes_to_process = []
    for text_node in content_node.descendants:
        if not isinstance(text_node, NavigableString):
            continue
        parent = text_node.find_parent()
        if not parent:
            continue
        if parent.name in ["script", "style"]:
            continue
        if parent.find_parent("a"):
            continue
        footnote_parent = parent.find_parent(class_=re.compile(r"(footnote|endnote|note)", re.I))
        if footnote_parent:
            continue

        text = str(text_node.string)
        if "[" in text and "]" in text:
            matches = list(footnote_pattern.finditer(text))
            if matches:
                text_nodes_to_process.append((text_node, parent, text, matches))

    for text_node, parent, text, matches in text_nodes_to_process:
        parts = []
        last_pos = 0
        matched_any = False

        for match in matches:
            if match.start() > last_pos:
                parts.append(NavigableString(text[last_pos:match.start()]))

            footnote_num = match.group(1)

            footnote_content = None
            key_variants = [
                footnote_num,
                f"n{footnote_num}",
                f"note{footnote_num}",
                f"footnote{footnote_num}",
                f"#{footnote_num}",
                f"fn{footnote_num}",
            ]

            for key in key_variants:
                key_lower = key.lower()
                if key_lower in footnotes:
                    footnote_content = footnotes[key_lower]
                    break

            if not footnote_content:
                for key, value in footnotes.items():
                    if key == footnote_num or key == f"n{footnote_num}":
                        footnote_content = value
                        break
                    if re.search(rf"\b{footnote_num}\b", key):
                        num_in_key = re.search(r"(\d+)", key)
                        if num_in_key and num_in_key.group(1) == footnote_num:
                            footnote_content = value
                            break

            if footnote_content:
                placeholder = soup.new_tag("latexfootnote")
                placeholder["content"] = footnote_content
                parts.append(placeholder)
                manual_matched += 1
                matched_any = True
            else:
                parts.append(NavigableString(match.group(0)))
                if len(manual_unmatched) < 5:
                    manual_unmatched.append(f"[{footnote_num}]")
                    if len(manual_unmatched) == 1:
                        available_keys = list(footnotes.keys())[:10]
                        log_fn(f"Debug: Available footnote keys (first 10): {available_keys}")

            last_pos = match.end()

        if last_pos < len(text):
            parts.append(NavigableString(text[last_pos:]))

        if matched_any:
            text_node.extract()
            for part in parts:
                parent.append(part)

    if manual_unmatched:
        log_fn(f"Warning: {len(manual_unmatched)} manual footnote references had no match: {', '.join(manual_unmatched[:5])}")
    if manual_matched > 0:
        log_fn(f"Converted {manual_matched} manual footnote references to endnotes.")

    return manual_matched
