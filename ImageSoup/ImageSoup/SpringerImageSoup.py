import re
import json
import urllib.request
from bs4 import BeautifulSoup

from ImageSoup.ImageSoup.BaseSoup import BaseSoup


class SpringerSoup(BaseSoup):

    def _extract_pdf_captions(self, pdf_path):
        """
        Extract Figure N captions from a Springer article PDF.

        Returns:
            dict: {figure_number: caption}
        """

        import subprocess
        import re

        txt_path = str(pdf_path) + ".txt"

        subprocess.check_call([
            "pdftotext",
            "-layout",
            str(pdf_path),
            txt_path
        ])

        with open(txt_path, "r", encoding="utf-8") as f:
            text = f.read()

        lines = text.splitlines()
        captions = {}

        for i, line in enumerate(lines):

            match = re.match(
                r'^\s*Figure\s+(\d+)\s+(.*)$',
                line,
                re.IGNORECASE
            )

            if not match:
                continue

            number = int(match.group(1))
            first_text = match.group(2).strip()

            # Ignore normal article references such as:
            # "Figure 3 shows..."
            # "Figure 3 also shows..."
            if re.match(
                r'^(shows|also shows|is|was|were|can|could|illustrates)\b',
                first_text,
                re.IGNORECASE
            ):
                continue

            parts = [first_text]
            j = i + 1

            while j < len(lines):

                current = lines[j].strip()

                if not current:
                    break

                if re.match(
                    r'^Figure\s+\d+\b',
                    current,
                    re.IGNORECASE
                ):
                    break

                if re.match(
                    r'^J Mater Sci \(',
                    current,
                    re.IGNORECASE
                ):
                    break

                parts.append(current)
                j += 1

            caption = " ".join(parts)

            # Remove Springer page header/footer accidentally
            # attached to the caption.
            caption = re.sub(
                r'\s*J Mater Sci \(.*?\)\s*\d+\s*$',
                '',
                caption,
                flags=re.IGNORECASE
            ).strip()

            # Keep the first valid occurrence.
            if number not in captions:
                captions[number] = caption

        return captions


    def _extract_images(self, images, captions=None):
        image_meta = {'figures':[]}

        if captions is None:
            captions = {}

        for image in images:

            # Old Springer HTML structure
            title_tag = image.find(
                'span',
                attrs={'class': 'CaptionNumber'}
            )

            caption_tag = image.find(
                'p',
                attrs={'class': 'SimplePara'}
            )

            link_tag = image.find('a')

            # Current Springer HTML structure
            if title_tag is None:
                title_tag = image.find(
                    'b',
                    attrs={'class': 'c-article-section__figure-caption'}
                )

            if link_tag is not None:
                img_url = link_tag.get('href')
            else:
                image_tag = image.find('img')
                img_url = image_tag.get('src') if image_tag else None

            if title_tag is None or img_url is None:
                continue

            title = title_tag.get_text(" ", strip=True)

            if caption_tag is not None:
                caption = caption_tag.get_text(" ", strip=True)
            else:
                caption = title

            # Current Springer image URLs may start with //
            if img_url.startswith('//'):
                img_url = 'https:' + img_url

            # Prefer the larger Springer image variant.
            if 'media.springernature.com/m312/' in img_url:
                img_url = img_url.replace(
                    'media.springernature.com/m312/',
                    'media.springernature.com/lw1200/'
                )

            figure_match = re.search(r'(\d+)', title)
            figure_number = (
                int(figure_match.group(1))
                if figure_match
                else None
            )

            if figure_number in captions:
                caption = captions[figure_number]

            image_meta['figures'].append({
                'Image_URL': img_url,
                'Caption': caption,
                'Title': title
            })

        return image_meta

    def _parse(self, html_string, **kwargs) -> dict:
        paper = BeautifulSoup(html_string, 'html.parser')
        images = paper.find_all('figure')

        captions = None

        pdf_path = kwargs.get('pdf_path')

        if pdf_path:
            captions = self._extract_pdf_captions(pdf_path)

        return self._extract_images(images, captions)
