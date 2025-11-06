#!/usr/bin/env python3
import argparse
import json
import os
from PIL import Image, ImageDraw, ImageFont


def load_corrections(corrections_file="corrections.json"):
    with open(corrections_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('corrections', []), data.get('overall_assessment', {})


def get_font(size=20):
    try:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/System/Library/Fonts/Arial.ttf",  # macOS
            "arial.ttf",  # Windows
        ]
        for font_path in font_paths:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
    except Exception:
        pass
    return ImageFont.load_default()


def draw_overall_assessment(draw, assessment, img_width, img_height, font_size, y_offset=50):
    start_y = img_height + y_offset
    green_color = (0, 150, 0, 255)
    red_color = (220, 0, 0, 255)
    blue_color = (0, 0, 180, 255)
    black_color = (0, 0, 0, 255)
    font = get_font(font_size)

    current_y = start_y
    line_spacing = int(font_size * 1.5)

    draw.text((20, current_y), "OVERALL ASSESSMENT", fill=black_color, font=font)
    current_y += line_spacing + 10

    final_status = assessment.get('final_answer_status', 'Not provided')
    status_color = green_color if final_status == 'correct' else red_color if final_status == 'incorrect' else (255, 165, 0, 255)

    draw.text((20, current_y), "Final Answer:", fill=blue_color, font=font)
    current_y += line_spacing
    draw.text((40, current_y), f"- {final_status.upper()}", fill=status_color, font=font)
    current_y += line_spacing

    strengths = assessment.get('key_strengths', 'Not provided')
    if strengths and strengths != 'Not provided':
        draw.text((20, current_y), "Key Strengths:", fill=blue_color, font=font)
        current_y += line_spacing
        max_width = img_width - 80
        for line in wrap_text(strengths, font, max_width):
            draw.text((40, current_y), f"• {line}", fill=green_color, font=font)
            current_y += line_spacing - 5
        current_y += 10

    improvements = assessment.get('areas_for_improvement', 'Not provided')
    if improvements and improvements != 'Not provided':
        draw.text((20, current_y), "Areas for Improvement:", fill=blue_color, font=font)
        current_y += line_spacing
        max_width = img_width - 80
        for line in wrap_text(improvements, font, max_width):
            draw.text((40, current_y), f"• {line}", fill=red_color, font=font)
            current_y += line_spacing - 5
        current_y += 10

    return current_y


def wrap_text(text, font, max_width):
    words = text.split()
    lines = []
    current_line = []
    test_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    for word in words:
        test_line = ' '.join(current_line + [word])
        try:
            bbox = test_draw.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]
        except Exception:
            text_width, _ = test_draw.textsize(test_line, font=font)
        if text_width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(word)
    if current_line:
        lines.append(' '.join(current_line))
    return lines


def create_overlay(image_path, corrections, assessment, font_size=32, output_path="corrected_overlay.png"):
    original = Image.open(image_path).convert('RGBA')
    img_width, img_height = original.size

    assessment_height = int(font_size * 20)
    total_height = img_height + assessment_height

    overlay = Image.new('RGBA', (img_width, total_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = get_font(font_size)
    mark_size = int(font_size * 1.2)

    for correction in corrections:
        bbox = correction.get('bbox') or {}
        if not bbox:
            continue
        top_left = tuple(bbox.get('top_left', [0, 0]))
        bottom_right = tuple(bbox.get('bottom_right', [0, 0]))
        status = correction.get('status', 'incorrect')
        marking = correction.get('marking', 'rectangle')

        width = bottom_right[0] - top_left[0]
        height = bottom_right[1] - top_left[1]
        if width <= 0 or height <= 0:
            continue

        if status == 'correct':
            check_x = bottom_right[0] + 10
            check_y = (top_left[1] + bottom_right[1]) // 2
            draw.line([(check_x, check_y), (check_x + int(mark_size / 1.5), check_y + int(mark_size / 1.5))], fill=(0, 180, 0, 255), width=8)
            draw.line([(check_x + int(mark_size / 1.5), check_y + int(mark_size / 1.5)), (check_x + int(mark_size * 2.0), check_y - int(mark_size / 2))], fill=(0, 180, 0, 255), width=8)
        elif status == 'incorrect':
            if marking == 'circle':
                padding = mark_size // 4
                circle_box = [
                    (top_left[0] - padding, top_left[1] - padding),
                    (bottom_right[0] + padding, bottom_right[1] + padding)
                ]
                draw.ellipse(circle_box, outline=(240, 30, 30, 255), width=5)
            else:
                padding = mark_size // 5
                rect_box = [
                    (top_left[0] - padding, top_left[1] - padding),
                    (bottom_right[0] + padding, bottom_right[1] + padding)
                ]
                draw.rectangle(rect_box, outline=(240, 30, 30, 255), width=5)

            corrected_text = correction.get('corrected_text', '')
            if corrected_text and corrected_text != correction.get('original_text', ''):
                test_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
                try:
                    text_bbox = test_draw.textbbox((0, 0), corrected_text, font=font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                except Exception:
                    text_width, text_height = test_draw.textsize(corrected_text, font=font)

                text_x = bottom_right[0] + mark_size + 10
                text_y = top_left[1]
                if text_x + text_width > img_width:
                    text_x = top_left[0] - text_width - 10
                    if text_x < 0:
                        text_x = top_left[0]
                        text_y = top_left[1] - text_height - 5
                        if text_y < 0:
                            text_y = bottom_right[1] + 5
                text_x = max(0, min(text_x, img_width - text_width))
                text_y = max(0, min(text_y, img_height - text_height))
                draw.text((text_x, text_y), corrected_text, fill=(200, 0, 0, 255), font=font)
        elif status == 'ignore':
            pass

    draw_overall_assessment(draw, assessment, img_width, img_height, font_size)

    overlay.save(output_path)

    extended_original = Image.new('RGBA', (img_width, total_height), (255, 255, 255, 255))
    extended_original.paste(original, (0, 0))
    composite = Image.alpha_composite(extended_original, overlay)
    composite_path = output_path.replace('.png', '_complete.png')
    composite.save(composite_path)

    return output_path, composite_path


def main():
    ap = argparse.ArgumentParser(description='Create overlay from corrections JSON')
    ap.add_argument('--image', required=True, help='Path to source image')
    ap.add_argument('--corrections', required=True, help='Path to corrections.json')
    ap.add_argument('--output', default='corrected_overlay.png', help='Output PNG path')
    ap.add_argument('--font-size', type=int, default=32)
    args = ap.parse_args()

    corrections, assessment = load_corrections(args.corrections)
    create_overlay(args.image, corrections, assessment, args.font_size, args.output)


if __name__ == '__main__':
    main()
