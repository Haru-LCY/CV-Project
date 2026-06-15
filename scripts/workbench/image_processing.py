from __future__ import annotations

import base64
from collections import deque
from io import BytesIO

from PIL import Image, ImageFilter, ImageOps


class DesktopPetImageProcessor:
    def _make_desktop_pet_standee(self, image_base64: str) -> str:
        image_bytes = base64.b64decode(image_base64)
        with Image.open(BytesIO(image_bytes)) as image:
            rgba = image.convert("RGBA")

        alpha = self._white_background_alpha(rgba)
        character = rgba.copy()
        character.putalpha(alpha)
        character = self._crop_to_alpha(character, padding=28)
        outlined = self._add_standee_outline(character)
        return self._encode_png_base64(outlined)

    def _white_background_alpha(self, image: Image.Image) -> Image.Image:
        rgb = image.convert("RGB")
        pixels = rgb.load()
        width, height = rgb.size
        background = Image.new("L", rgb.size, 0)
        background_pixels = background.load()
        visited: set[tuple[int, int]] = set()
        queue: deque[tuple[int, int]] = deque()

        for x in range(width):
            queue.append((x, 0))
            queue.append((x, height - 1))
        for y in range(height):
            queue.append((0, y))
            queue.append((width - 1, y))

        while queue:
            x, y = queue.popleft()
            if (x, y) in visited:
                continue
            visited.add((x, y))
            if not self._is_background_white(pixels[x, y]):
                continue
            background_pixels[x, y] = 255
            if x > 0:
                queue.append((x - 1, y))
            if x + 1 < width:
                queue.append((x + 1, y))
            if y > 0:
                queue.append((x, y - 1))
            if y + 1 < height:
                queue.append((x, y + 1))

        background = background.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.0))
        return ImageOps.invert(background)

    def _is_background_white(self, color: tuple[int, int, int]) -> bool:
        r, g, b = color
        return min(r, g, b) >= 235 and max(r, g, b) - min(r, g, b) <= 42

    def _crop_to_alpha(self, image: Image.Image, padding: int) -> Image.Image:
        bbox = image.getchannel("A").getbbox()
        if not bbox:
            return image
        left = max(0, bbox[0] - padding)
        top = max(0, bbox[1] - padding)
        right = min(image.width, bbox[2] + padding)
        bottom = min(image.height, bbox[3] + padding)
        return image.crop((left, top, right, bottom))

    def _add_standee_outline(self, character: Image.Image) -> Image.Image:
        alpha = character.getchannel("A")
        outline_outer = alpha.filter(ImageFilter.MaxFilter(19)).filter(ImageFilter.GaussianBlur(1.6))
        outline_inner = alpha.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(0.8))

        padding = 18
        canvas_size = (character.width + padding * 2, character.height + padding * 2)
        canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        outer_layer = Image.new("RGBA", canvas_size, (255, 255, 255, 0))
        inner_layer = Image.new("RGBA", canvas_size, (255, 236, 246, 0))
        shadow_layer = Image.new("RGBA", canvas_size, (105, 78, 96, 0))

        outer_alpha = Image.new("L", canvas_size, 0)
        inner_alpha = Image.new("L", canvas_size, 0)
        shadow_alpha = Image.new("L", canvas_size, 0)
        outer_alpha.paste(outline_outer, (padding, padding))
        inner_alpha.paste(outline_inner, (padding, padding))
        shadow_alpha.paste(alpha.filter(ImageFilter.MaxFilter(13)).filter(ImageFilter.GaussianBlur(4.0)), (padding + 3, padding + 5))

        outer_layer.putalpha(outer_alpha.point(lambda value: min(255, int(value * 0.96))))
        inner_layer.putalpha(inner_alpha.point(lambda value: min(210, int(value * 0.72))))
        shadow_layer.putalpha(shadow_alpha.point(lambda value: min(80, int(value * 0.24))))

        canvas.alpha_composite(shadow_layer)
        canvas.alpha_composite(outer_layer)
        canvas.alpha_composite(inner_layer)
        canvas.alpha_composite(character, (padding, padding))
        return canvas

    def _encode_png_base64(self, image: Image.Image) -> str:
        output = BytesIO()
        image.save(output, format="PNG")
        return base64.b64encode(output.getvalue()).decode("utf-8")


DEFAULT_IMAGE_PROCESSOR = DesktopPetImageProcessor()


def make_desktop_pet_standee(image_base64: str) -> str:
    return DEFAULT_IMAGE_PROCESSOR._make_desktop_pet_standee(image_base64)
