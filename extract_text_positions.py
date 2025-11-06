#!/usr/bin/env python3
import argparse
import json
import os
from typing import List, Dict, Tuple

from PIL import Image, ImageDraw, ImageFont
from google.cloud import vision

from config import get_vision_client


BBox = Dict[str, List[int]]
Box = Dict[str, object]


def extract_text_with_positions(image_path: str, use_adaptive_config: bool = True, custom_config: Dict = None) -> List[Box]:
    client = get_vision_client()

    with open(image_path, 'rb') as f:
        content = f.read()
    img = Image.open(image_path)
    img_width, img_height = img.size

    image = vision.Image(content=content)
    response = client.document_text_detection(image=image)
    if response.error.message:
        raise RuntimeError(f"Vision API error: {response.error.message}")

    full_text = response.full_text_annotation

    words: List[Box] = []
    for page in full_text.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    text = ''.join([s.text for s in word.symbols])
                    text = text.strip()
                    if not text:
                        continue
                    vertices = word.bounding_box.vertices
                    x_coords = [v.x for v in vertices]
                    y_coords = [v.y for v in vertices]
                    bbox: BBox = {
                        "top_left": [min(x_coords), min(y_coords)],
                        "bottom_right": [max(x_coords), max(y_coords)],
                        "width": max(x_coords) - min(x_coords),
                        "height": max(y_coords) - min(y_coords),
                    }
                    words.append({
                        "id": len(words),
                        "text": text,
                        "confidence": float(getattr(word, 'confidence', 0.5) or 0.5),
                        "bbox": bbox,
                    })

    # Optional simple grouping: merge horizontally close boxes on same line
    config = custom_config or {}
    if use_adaptive_config and not custom_config:
        config = adaptive_grouping_config(img_width, img_height)
    grouped = improved_group_nearby_boxes(words, config)
    return grouped


def calculate_box_center(bbox: BBox) -> Tuple[float, float]:
    x1, y1 = bbox['top_left']
    x2, y2 = bbox['bottom_right']
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def boxes_are_horizontally_aligned(box1: Box, box2: Box, tolerance: float = 30) -> bool:
    return abs(calculate_box_center(box1['bbox'])[1] - calculate_box_center(box2['bbox'])[1]) <= tolerance


def boxes_are_vertically_aligned(box1: Box, box2: Box, tolerance: float = 50) -> bool:
    return abs(calculate_box_center(box1['bbox'])[0] - calculate_box_center(box2['bbox'])[0]) <= tolerance


def calculate_gap_between_boxes(box1: Box, box2: Box) -> float:
    x1_right = box1['bbox']['bottom_right'][0]
    x2_left = box2['bbox']['top_left'][0]
    if x2_left >= x1_right:
        return x2_left - x1_right
    x2_right = box2['bbox']['bottom_right'][0]
    x1_left = box1['bbox']['top_left'][0]
    if x1_left >= x2_right:
        return x1_left - x2_right
    return 0.0


def should_merge_boxes(box1: Box, box2: Box, config: Dict) -> bool:
    max_horizontal_gap = int(config.get('max_horizontal_gap', 80))
    max_vertical_gap = int(config.get('max_vertical_gap', 40))
    h_tol = int(config.get('horizontal_alignment_tolerance', 25))
    v_tol = int(config.get('vertical_alignment_tolerance', 40))

    if boxes_are_horizontally_aligned(box1, box2, h_tol):
        gap = calculate_gap_between_boxes(box1, box2)
        if gap <= max_horizontal_gap:
            return True
    if boxes_are_vertically_aligned(box1, box2, v_tol):
        b1 = box1['bbox']['bottom_right'][1]
        t2 = box2['bbox']['top_left'][1]
        if t2 >= b1 and (t2 - b1) <= max_vertical_gap:
            return True
        b2 = box2['bbox']['bottom_right'][1]
        t1 = box1['bbox']['top_left'][1]
        if t1 >= b2 and (t1 - b2) <= max_vertical_gap:
            return True
    return False


def merge_boxes(boxes: List[Box]) -> Box:
    if not boxes:
        raise ValueError("No boxes to merge")
    if len(boxes) == 1:
        return boxes[0]
    sorted_boxes = sorted(boxes, key=lambda x: (x['bbox']['top_left'][1], x['bbox']['top_left'][0]))
    xs: List[int] = []
    ys: List[int] = []
    for b in sorted_boxes:
        x1, y1 = b['bbox']['top_left']
        x2, y2 = b['bbox']['bottom_right']
        xs.extend([x1, x2])
        ys.extend([y1, y2])
    merged_bbox: BBox = {
        'top_left': [min(xs), min(ys)],
        'bottom_right': [max(xs), max(ys)],
        'width': max(xs) - min(xs),
        'height': max(ys) - min(ys),
    }
    text = ' '.join([b['text'] for b in sorted_boxes])
    conf = sum([float(b.get('confidence', 0.5)) for b in sorted_boxes]) / len(sorted_boxes)
    return {
        'id': sorted_boxes[0]['id'],
        'text': text,
        'confidence': round(conf, 3),
        'bbox': merged_bbox,
        'original_boxes': len(sorted_boxes),
    }


def improved_group_nearby_boxes(text_data: List[Box], config: Dict = None) -> List[Box]:
    if not text_data:
        return text_data
    if config is None:
        config = {
            'max_horizontal_gap': 80,
            'max_vertical_gap': 40,
            'horizontal_alignment_tolerance': 25,
            'vertical_alignment_tolerance': 40,
        }
    boxes = [b.copy() for b in text_data]
    grouped: List[Box] = []
    used = set()
    for i, current in enumerate(boxes):
        if i in used:
            continue
        group = [current]
        used.add(i)
        changed = True
        while changed:
            changed = False
            for j, cand in enumerate(boxes):
                if j in used:
                    continue
                if any(should_merge_boxes(g, cand, config) for g in group):
                    group.append(cand)
                    used.add(j)
                    changed = True
        merged = merge_boxes(group)
        merged['id'] = len(grouped)
        grouped.append(merged)
    return grouped


def adaptive_grouping_config(image_width: int, image_height: int) -> Dict:
    base = {
        'max_horizontal_gap': 80,
        'max_vertical_gap': 40,
        'horizontal_alignment_tolerance': 25,
        'vertical_alignment_tolerance': 40,
    }
    width_scale = max(1.0, image_width / 1000.0)
    height_scale = max(1.0, image_height / 1000.0)
    return {
        'max_horizontal_gap': int(base['max_horizontal_gap'] * width_scale),
        'max_vertical_gap': int(base['max_vertical_gap'] * height_scale),
        'horizontal_alignment_tolerance': int(base['horizontal_alignment_tolerance'] * height_scale),
        'vertical_alignment_tolerance': int(base['vertical_alignment_tolerance'] * width_scale),
    }


def visualize_bounding_boxes(image_path: str, text_data: List[Box], output_path: str = "visualized_boxes.jpg"):
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    colors = ["red", "green", "blue", "purple", "orange", "cyan", "magenta", "yellow"]
    for i, item in enumerate(text_data):
        box = item['bbox']
        x1, y1 = box['top_left']
        x2, y2 = box['bottom_right']
        text = item['text']
        color = colors[i % len(colors)]
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        label = f"ID:{item['id']} ({item.get('original_boxes',1)}): {text[:30]}..."
        try:
            font = ImageFont.truetype("arial.ttf", 12)
        except Exception:
            font = ImageFont.load_default()
        text_y = max(0, y1 - 20)
        if text_y + 16 > y1:
            text_y = y2 + 4
        bbox = draw.textbbox((x1, text_y), label, font=font)
        draw.rectangle(bbox, fill='white', outline=color)
        draw.text((x1, text_y), label, fill=color, font=font)
    img.save(output_path)


def generate_chatgpt_prompt(text_data: List[Box], image_path: str) -> str:
    img = Image.open(image_path)
    img_width, img_height = img.size
    sorted_data = sorted(text_data, key=lambda x: (x['bbox']['top_left'][1], x['bbox']['top_left'][0]))

    prompt = f"You are an experienced mathematics and english teacher evaluating a student's handwritten solution. Focus on math/grammar; be tolerant to handwriting.\n\nImage size: {img_width}x{img_height} pixels\n\nDETECTED TEXT REGIONS:\n"
    for item in sorted_data:
        box = item['bbox']
        x1, y1 = box['top_left']
        prompt += (
            f"Region {item['id']}:\n"
            f"Position: [{x1},{y1}] to [{box['bottom_right'][0]},{box['bottom_right'][1]}]\n"
            f"Student wrote: \"{item['text']}\"\n---\n"
        )

    prompt += "\nReturn strict JSON with fields: corrections[id,status,original_text,mathematical_interpretation,corrected_text,reasoning,marking,bbox{top_left,bottom_right},scratched], and overall_assessment{key_strengths,areas_for_improvement,final_answer_status}."
    return prompt


def main():
    ap = argparse.ArgumentParser(description="Extract OCR boxes and build prompt")
    ap.add_argument('--image', required=True)
    ap.add_argument('--out-dir', default='outputs')
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    data = extract_text_with_positions(args.image)
    visualize_bounding_boxes(args.image, data, os.path.join(args.out_dir, 'visualized_boxes.jpg'))
    prompt = generate_chatgpt_prompt(data, args.image)
    with open(os.path.join(args.out_dir, 'chatgpt_prompt.txt'), 'w', encoding='utf-8') as f:
        f.write(prompt)
    with open(os.path.join(args.out_dir, 'ocr_data.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    with open(os.path.join(args.out_dir, 'image_info.json'), 'w', encoding='utf-8') as f:
        json.dump({'image_path': args.image}, f, indent=2)


if __name__ == '__main__':
    main()
