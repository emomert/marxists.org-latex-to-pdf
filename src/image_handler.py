from bs4 import BeautifulSoup, Tag


def handle_images(soup: BeautifulSoup, node: Tag, page_url: str, images_dir: str) -> None:
    _ = soup, page_url, images_dir
    if not node:
        return
    for img in node.find_all("img"):
        img.decompose()
