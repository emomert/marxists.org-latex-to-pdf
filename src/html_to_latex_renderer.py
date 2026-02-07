import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import Comment, NavigableString, Tag

from .utils import clean_text_fragments, clean_text_node, escape_latex


class HtmlToLatexRenderer:
    def render(self, element, base_url: str = "") -> str:
        if isinstance(element, Comment):
            return ""
        if isinstance(element, NavigableString):
            text = clean_text_node(str(element))
            if not text:
                return ""
            return escape_latex(text)
        if not isinstance(element, Tag):
            return ""
        name = element.name.lower()

        def convert_children(tag: Tag) -> str:
            return "".join(self.render(child, base_url) for child in tag.children)

        if name == "latexfootnote":
            content = clean_text_fragments(element.get("content", ""))
            if not content:
                return ""
            if re.match(r"^(MIA|Archive).*>(Archive|.*>.*)", content, re.I):
                return ""
            return f"\\endnote{{{escape_latex(content)}}}"
        if name == "lateximage":
            path = element.get("path", "")
            path = path.replace("\\", "/")
            return (
                "\\begin{figure}[H]\\centering"
                f"\\includegraphics[width=0.9\\linewidth]{{{path}}}"
                "\\end{figure}"
            )
        if name in ["p", "div", "center"]:
            classes = element.get("class", [])
            if classes and any("quote" in c.lower() for c in classes):
                body = self._normalize_block(convert_children(element))
                return "\\begin{quoting}\n" + body + "\n\\end{quoting}\n\n"
            if classes and any("indentb" in c.lower() for c in classes):
                raw = convert_children(element)
                lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
                body = " \\\\n".join(lines)
                body = self._normalize_block(body)
                return "\\begin{quote}\n" + body + "\n\\end{quote}\n\n"
            if classes and any("inline" == c.lower() for c in classes):
                content = convert_children(element)
                return f"\\begin{{flushright}}\n{content}\n\\end{{flushright}}\n\n"
            return convert_children(element) + "\n\n"
        if name == "br":
            return "\n"
        if name in ["em", "i", "cite"]:
            return f"\\textit{{{convert_children(element)}}}"
        if name in ["strong", "b"]:
            return f"\\textbf{{{convert_children(element)}}}"
        if name in ["span", "font"]:
            classes = element.get("class", [])
            if classes and any("inline" == c.lower() for c in classes):
                return f"\\begin{{flushright}}{convert_children(element)}\\end{{flushright}}"
            return convert_children(element)

        if name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(name[1])
            return self._convert_heading(element, level, convert_children)
        if name == "blockquote":
            body = self._normalize_block(convert_children(element))
            if "\\begin{quoting}" in body:
                return body + "\n\n"
            return "\\begin{quoting}\n" + body + "\n\\end{quoting}\n\n"
        if name == "ul":
            items = "".join("\\item " + convert_children(li) + "\n" for li in element.find_all("li", recursive=False))
            return "\\begin{itemize}\n" + items + "\\end{itemize}\n\n"
        if name == "ol":
            items = "".join("\\item " + convert_children(li) + "\n" for li in element.find_all("li", recursive=False))
            return "\\begin{enumerate}\n" + items + "\\end{enumerate}\n\n"
        if name == "li":
            return "\\item " + convert_children(element) + "\n"
        if name == "table":
            return self._convert_table(element, convert_children)
        if name in ["tbody", "thead", "tfoot", "tr", "td", "th"]:
            return convert_children(element)
        if name == "a":
            href = element.get("href")
            text = convert_children(element)
            if href:
                if href.startswith("#"):
                    return text
                if not href.startswith("http"):
                    if base_url:
                        href = urljoin(base_url, href)
                    else:
                        return text
                return f"\\href{{{escape_latex(href)}}}{{{text}}}"
            return text
        return convert_children(element)

    def _convert_heading(self, element: Tag, level: int, convert_children) -> str:
        heading_text = element.get_text(strip=True).lower()
        if heading_text in ["notes", "note", "footnotes", "endnotes"]:
            return ""
        if self._is_navigation_heading(element):
            return ""
        content = self._clean_heading_content(convert_children(element))
        if not content:
            return ""
        content = content.replace("\n", " ").replace("\r", " ").strip()
        if level == 1:
            return f"\\section*{{{content}}}\n\n"
        if level == 2:
            return f"\\subsection*{{{content}}}\n\n"
        if level == 3:
            return f"\\subsubsection*{{{content}}}\n\n"
        if level == 4:
            return f"\\subsection*{{{content}}}\n\n"
        return f"\\paragraph*{{{content}}}\\mbox{{}}\\\\\n\n"

    def _convert_table(self, element: Tag, convert_children) -> str:
        table_class = element.get("class", [])
        if table_class and any("foot" in c.lower() or "nav" in c.lower() for c in table_class):
            return ""

        if element.find(["ol", "ul", "li"]):
            return self._table_to_text(element, in_blockquote=bool(element.find_parent("blockquote")))

        nested_inner = element.find("table")
        if nested_inner:
            rendered = self._convert_nested_value_form_table(element, convert_children)
            if rendered:
                return rendered
            return self._table_to_text(element, in_blockquote=bool(element.find_parent("blockquote")))

        rows = element.find_all("tr")
        if not rows:
            return ""

        if len(rows) == 1:
            cells = rows[0].find_all(["td", "th"])
            if len(cells) == 1:
                cell = cells[0]
                parent = element.find_parent("blockquote")
                if self._is_poetry_cell(cell):
                    formatted_content = self._extract_and_format_poetry(cell)
                    if parent:
                        return f"{formatted_content}\n\n"
                    return "\\begin{center}\n\\begin{quoting}\n" + formatted_content + "\n\\end{quoting}\n\\end{center}\n\n"
                cell_content = convert_children(cell)
                if cell_content.strip():
                    if parent:
                        return self._normalize_block(cell_content) + "\n\n"
                    return "\\begin{quoting}\n" + self._normalize_block(cell_content) + "\n\\end{quoting}\n\n"
                return ""

        if self._is_section_list_table(rows, convert_children):
            table_rows = []
            for row in rows:
                cells = row.find_all(["td", "th"], recursive=False)
                if len(cells) == 1 and cells[0].get("colspan") == "2":
                    table_rows.append("\\hline")
                    continue
                if row.find("hr"):
                    table_rows.append("\\hline")
                    continue

                if len(cells) == 2:
                    left_content = convert_children(cells[0])
                    left_content_clean = escape_latex(left_content.strip())
                    if re.match(r"^[IVX]+\.\s*[A-Z\s]+$", left_content_clean, re.I):
                        left_content_clean = f"\\textbf{{{left_content_clean}}}"
                    right_content = convert_children(cells[1])
                    right_content = self._normalize_block(right_content)
                    table_rows.append(f"{left_content_clean} & {right_content} \\\\")

            if table_rows:
                table_content = "\n".join(table_rows)
                return (
                    "\\begin{center}\n"
                    "\\begin{tabular}{>{\\raggedleft\\arraybackslash}p{0.22\\textwidth}|p{0.73\\textwidth}}\n"
                    "\\renewcommand{\\arraystretch}{1.1}\n"
                    "\\setlength{\\tabcolsep}{0.8em}\n"
                    f"{table_content}\n"
                    "\\end{tabular}\n"
                    "\\end{center}\n\n"
                )

        if self._is_numbered_list_table(rows):
            result = self._convert_numbered_list_table(rows)
            if result:
                return result

        parent = element.find_parent("blockquote")
        in_blockquote = parent is not None

        return self._table_to_text(element, in_blockquote=in_blockquote)

    def _clean_heading_content(self, raw: str) -> str:
        cleaned = re.sub(r"\\endnote\{[^}]*\}", "", raw)
        cleaned = re.sub(r"\s*>>\s*", "", cleaned)
        cleaned = re.sub(r"\s*<<\s*", "", cleaned)
        cleaned = re.sub(r"\\href\{[^}]+\}\{[^}]+\}", "", cleaned)
        cleaned = re.sub(r"\s*\|\s*", " ", cleaned)
        if re.match(r"^(MIA|Archive).*>(Archive|.*>.*)", cleaned, re.I):
            return ""
        if re.match(r"^Top\s+of\s+the\s+page\s*$", cleaned, re.I):
            return ""
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _is_navigation_heading(self, elem: Tag) -> bool:
        raw_text = elem.get_text(strip=True)
        has_nav_arrows = ">>" in raw_text or "<<" in raw_text
        has_nav_text = "top of the page" in raw_text.lower()
        has_nav_links = len(elem.find_all("a", href=True)) > 0 and ("contents" in raw_text.lower() or "page" in raw_text.lower())
        return has_nav_arrows or has_nav_text or has_nav_links

    def _strip_trailing_breaks(self, text: str) -> str:
        text = text.rstrip()
        text = re.sub(r"(\\\\\s*)+$", "", text)
        return text

    def _strip_leading_breaks(self, text: str) -> str:
        text = text.lstrip()
        text = re.sub(r"^(\\\\\s*)+", "", text)
        return text

    def _normalize_block(self, text: str) -> str:
        text = text or ""
        text = self._strip_leading_breaks(self._strip_trailing_breaks(text))
        lines = text.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    def _is_poetry_cell(self, cell: Tag) -> bool:
        br_tags = cell.find_all("br")
        if len(br_tags) >= 3:
            return True
        text_content = cell.get_text("\n", strip=True)
        lines = [line.strip() for line in text_content.split("\n") if line.strip()]
        if len(lines) >= 3:
            short_lines = sum(1 for line in lines if len(line) < 80)
            if short_lines >= len(lines) * 0.7:
                return True
        return False

    def _extract_and_format_poetry(self, cell: Tag) -> str:
        lines = []
        current_line_parts = []

        def extract_inline_content(elem):
            nonlocal current_line_parts
            if isinstance(elem, NavigableString):
                text = clean_text_node(str(elem))
                if text:
                    current_line_parts.append(escape_latex(text))
            elif isinstance(elem, Tag):
                if elem.name == "latexfootnote":
                    content = clean_text_fragments(elem.get("content", ""))
                    if content:
                        current_line_parts.append(f"\\endnote{{{escape_latex(content)}}}")
                elif elem.name in ["em", "i", "cite"]:
                    text = elem.get_text(" ", strip=True)
                    if text:
                        current_line_parts.append(f"\\textit{{{escape_latex(text)}}}")
                elif elem.name in ["strong", "b"]:
                    text = elem.get_text(" ", strip=True)
                    if text:
                        current_line_parts.append(f"\\textbf{{{escape_latex(text)}}}")
                elif elem.name == "a":
                    text = elem.get_text(" ", strip=True)
                    if text:
                        current_line_parts.append(escape_latex(text))
                else:
                    for child in elem.children:
                        extract_inline_content(child)

        def process_poetry_element(elem):
            nonlocal current_line_parts
            if isinstance(elem, NavigableString):
                extract_inline_content(elem)
            elif isinstance(elem, Tag):
                if elem.name == "br":
                    if current_line_parts:
                        line_content = " ".join(current_line_parts).strip()
                        if line_content:
                            lines.append(line_content)
                        current_line_parts = []
                elif elem.name == "p":
                    for child in elem.children:
                        process_poetry_element(child)
                else:
                    extract_inline_content(elem)

        for child in cell.children:
            process_poetry_element(child)

        if current_line_parts:
            line_content = " ".join(current_line_parts).strip()
            if line_content:
                lines.append(line_content)

        lines = [line for line in lines if line.strip()]

        if not lines:
            return ""

        result_parts = []
        for i, line in enumerate(lines):
            if i > 0:
                result_parts.append(" \\\\")
            result_parts.append(f"\n{line}")

        return "".join(result_parts)

    def _format_poetry_content(self, content: str) -> str:
        content = re.sub(r"\\begin\{quoting\}\s*", "", content)
        content = re.sub(r"\\end\{quoting\}\s*", "", content)

        lines = content.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped:
                cleaned_lines.append(stripped)

        if not cleaned_lines:
            return content

        result_parts = []
        for i, line in enumerate(cleaned_lines):
            if i > 0:
                result_parts.append(" \\\\")
            result_parts.append(f"\n{line}")

        return "".join(result_parts)

    def _is_section_list_table(self, rows_list, convert_children) -> bool:
        if len(rows_list) < 2:
            return False
        section_count = 0
        list_count = 0
        for row in rows_list:
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) == 1 and cells[0].get("colspan") == "2":
                continue
            if row.find("hr"):
                continue
            if len(cells) == 2:
                left_text = cells[0].get_text(strip=True)
                right_elem = cells[1]
                if re.match(r"^[IVX]+\.\s+[A-Z\s]+$", left_text.strip()):
                    section_count += 1
                if right_elem.find("ol"):
                    list_count += 1
        return section_count >= 1 and list_count >= 1

    def _table_to_text(self, table: Tag, in_blockquote: bool = False) -> str:
        rows = table.find_all("tr")
        if not rows:
            return ""

        for lst in table.find_all(["ol", "ul"]):
            lst.replace_with(lst.get_text(" ", strip=True))

        lines = []
        for row in rows:
            cells = row.find_all(["td", "th"])
            cell_texts = []
            for cell in cells:
                text = cell.get_text(" ", strip=True)
                text = clean_text_fragments(text)
                if text:
                    escaped = escape_latex(text)
                    cell_texts.append(escaped)
            if cell_texts:
                row_text = " --- ".join(cell_texts)
                lines.append(row_text)

        if not lines:
            return ""

        content = "\n\n".join(lines)

        if in_blockquote:
            return f"\n{content}\n\n"

        return f"\n\\begin{{quoting}}\n{content}\n\\end{{quoting}}\n\n"

    def _is_numbered_list_table(self, rows: List[Tag]) -> bool:
        if not rows:
            return False

        number_pattern = re.compile(r"\(\d+\)")

        full_text = ""
        for row in rows:
            full_text += row.get_text()

        matches = number_pattern.findall(full_text)
        return len(matches) >= 2

    def _convert_numbered_list_table(self, rows: List[Tag]) -> str:
        all_cells = []
        for row in rows:
            all_cells.extend(row.find_all(["td", "th"]))

        if len(all_cells) < 2:
            return ""

        first_cell = all_cells[0]
        second_cell = all_cells[1] if len(all_cells) > 1 else None

        if not second_cell:
            return ""

        item_line_counts = self._parse_numbered_cell(first_cell)

        if len(item_line_counts) < 2:
            return ""

        content_lines = self._get_content_lines(second_cell)

        artifact_pattern = re.compile(r"vol=\d+\s*pg=\d+\s*src=\S*\s*type=\s*", re.I)
        content_lines = [artifact_pattern.sub("", line).strip() for line in content_lines]
        content_lines = [line for line in content_lines if line]

        items = []
        line_idx = 0
        for count in item_line_counts:
            item_parts = []
            for _ in range(count):
                if line_idx < len(content_lines):
                    item_parts.append(content_lines[line_idx])
                    line_idx += 1
            if item_parts:
                items.append(" ".join(item_parts))

        if line_idx < len(content_lines) and items:
            remaining = " ".join(content_lines[line_idx:])
            items[-1] = items[-1] + " " + remaining

        if items:
            item_strs = [f"\\item {escape_latex(item)}" for item in items]
            return "\\begin{enumerate}\n" + "\n".join(item_strs) + "\n\\end{enumerate}\n\n"

        return ""

    def _parse_numbered_cell(self, cell: Tag) -> List[int]:
        number_pattern = re.compile(r"^\s*\((\d+)\)\s*$")

        items_info = []
        current_number = None
        br_count = 0

        for child in cell.children:
            if isinstance(child, Tag) and child.name == "br":
                br_count += 1
            elif isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    match = number_pattern.match(text)
                    if match:
                        if current_number is not None:
                            items_info.append(br_count)
                        current_number = int(match.group(1))
                        br_count = 0

        if current_number is not None:
            items_info.append(max(br_count, 1))

        return items_info

    def _get_content_lines(self, cell: Tag) -> List[str]:
        lines = []
        current_parts = []

        for child in cell.children:
            if isinstance(child, Tag):
                if child.name == "br":
                    if current_parts:
                        lines.append(" ".join(current_parts))
                        current_parts = []
                elif child.name == "comment":
                    continue
                else:
                    text = child.get_text().strip()
                    if text:
                        current_parts.append(text)
            elif isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    current_parts.append(text)

        if current_parts:
            lines.append(" ".join(current_parts))

        return lines

    def _convert_nested_value_form_table(self, element: Tag, convert_children) -> str:
        outer_rows = element.find_all("tr", recursive=False)
        if len(outer_rows) != 1:
            return ""

        outer_cells = outer_rows[0].find_all("td", recursive=False)
        if len(outer_cells) < 2:
            return ""

        inner_table = None
        right_cell: Optional[Tag] = None
        for cell in outer_cells:
            nested = cell.find("table")
            if nested and inner_table is None:
                inner_table = nested
            else:
                text = clean_text_fragments(cell.get_text(" ", strip=True))
                if text:
                    right_cell = cell

        if not inner_table or right_cell is None:
            return ""

        inner_rows = inner_table.find_all("tr", recursive=False)
        if len(inner_rows) < 2:
            return ""

        left_items: List[str] = []
        has_equals_column = False
        for row in inner_rows:
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells:
                continue

            raw_texts = [clean_text_fragments(c.get_text(" ", strip=True)) for c in cells]
            if raw_texts and raw_texts[-1] == "=":
                has_equals_column = True
                cells = cells[:-1]

            parts: List[str] = []
            for cell in cells:
                content = convert_children(cell)
                content = self._normalize_block(content)
                content = content.replace("\n", " ").strip()
                content = re.sub(r"\s+", " ", content)
                if content:
                    parts.append(content)

            combined = " ".join(parts).strip()
            if combined:
                left_items.append(combined)

        if len(left_items) < 2:
            return ""

        right_content = convert_children(right_cell)
        right_content = self._normalize_block(right_content)
        right_content = right_content.replace("\n", " ").strip()
        right_content = re.sub(r"\s+", " ", right_content)
        if not right_content:
            return ""

        if not has_equals_column and not right_content.lstrip().startswith("="):
            right_content = f"= {right_content}"

        col_spec = (
            r">{\raggedleft\arraybackslash}p{0.38\textwidth} c|p{0.5\textwidth}"
            if has_equals_column
            else r">{\raggedleft\arraybackslash}p{0.42\textwidth}|p{0.5\textwidth}"
        )

        total_rows = len(left_items)
        table_rows: List[str] = []
        for idx, item in enumerate(left_items):
            if has_equals_column:
                if idx == 0:
                    table_rows.append(f"{item} & = & \\multirow{{{total_rows}}}{{*}}{{{right_content}}} \\\\")
                else:
                    table_rows.append(f"{item} & = & \\\\")
            else:
                if idx == 0:
                    table_rows.append(f"{item} & \\multirow{{{total_rows}}}{{*}}{{{right_content}}} \\\\")
                else:
                    table_rows.append(f"{item} & \\\\")

        return (
            "\\begin{center}\n"
            "\\setlength{\\tabcolsep}{1.1em}\n"
            "\\renewcommand{\\arraystretch}{1.15}\n"
            f"\\begin{{tabular}}{{{col_spec}}}\n"
            + "\n".join(table_rows)
            + "\n\\end{tabular}\n"
            "\\end{center}\n\n"
        )
