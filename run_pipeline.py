#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import pathlib
import sys

# Local imports
from extract_text_positions import (
    extract_text_with_positions,
    generate_chatgpt_prompt,
    visualize_bounding_boxes,
)
from gpt_corrections import get_corrections_from_prompt


def ensure_dir(p: str) -> str:
    pathlib.Path(p).mkdir(parents=True, exist_ok=True)
    return p


def run_pipeline(
    image_path: str,
    out_dir: str,
    use_ocr_json: str = None,
    use_corrections_json: str = None,
    skip_ocr: bool = False,
    skip_openai: bool = False,
) -> None:
    out_dir = ensure_dir(out_dir)

    # 1) Extract text + boxes
    if use_ocr_json:
        with open(use_ocr_json, 'r', encoding='utf-8') as f:
            text_data = json.load(f)
    elif not skip_ocr:
        text_data = extract_text_with_positions(image_path)
    else:
        with open(os.path.join(out_dir, 'ocr_data.json'), 'r', encoding='utf-8') as f:
            text_data = json.load(f)

    # 2) Visualize boxes
    boxes_img = os.path.join(out_dir, "visualized_boxes.jpg")
    try:
        visualize_bounding_boxes(image_path, text_data, boxes_img)
    except Exception:
        pass

    # 3) Build prompt
    prompt = generate_chatgpt_prompt(text_data, image_path)
    prompt_path = os.path.join(out_dir, "chatgpt_prompt.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    # 4) Call OpenAI (vision) for corrections
    if use_corrections_json:
        with open(use_corrections_json, 'r', encoding='utf-8') as f:
            corrections = json.load(f)
    elif not skip_openai:
        corrections = get_corrections_from_prompt(prompt, image_path)
    else:
        with open(os.path.join(out_dir, 'corrections.json'), 'r', encoding='utf-8') as f:
            corrections = json.load(f)

    corrections_path = os.path.join(out_dir, "corrections.json")
    with open(corrections_path, "w", encoding="utf-8") as f:
        json.dump(corrections, f, indent=2, ensure_ascii=False)

    # 5) Save OCR data and image info
    with open(os.path.join(out_dir, "ocr_data.json"), "w", encoding="utf-8") as f:
        json.dump(text_data, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "image_info.json"), "w", encoding="utf-8") as f:
        json.dump({"image_path": image_path}, f, indent=2)

    # 6) Create overlays
    from create_overlay import create_overlay
    overlay_png = os.path.join(out_dir, "corrected_overlay.png")
    overlay_path, composite_path = create_overlay(
        image_path,
        corrections.get("corrections", []),
        corrections.get("overall_assessment", {}),
        font_size=32,
        output_path=overlay_png,
    )

    print("Pipeline complete.")
    print(f"- Boxes: {boxes_img}")
    print(f"- Prompt: {prompt_path}")
    print(f"- Corrections: {corrections_path}")
    print(f"- Overlay: {overlay_path}")
    print(f"- Composite: {composite_path}")


def main():
    ap = argparse.ArgumentParser(description="OCR -> Prompt -> OpenAI (vision) -> Overlay pipeline")
    ap.add_argument("--image", required=True, help="Path to source image")
    ap.add_argument("--out-dir", default=None, help="Output directory (default: outputs/<timestamp>)")
    ap.add_argument("--use-ocr-json", default=None, help="Use existing OCR JSON instead of calling Vision")
    ap.add_argument("--use-corrections", default=None, help="Use existing corrections JSON instead of calling OpenAI")
    ap.add_argument("--skip-ocr", action="store_true", help="Skip Vision (expects ocr_data.json in out-dir)")
    ap.add_argument("--skip-openai", action="store_true", help="Skip OpenAI (expects corrections.json in out-dir)")
    args = ap.parse_args()

    image_path = args.image
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        sys.exit(1)

    out_dir = args.out_dir or os.path.join("outputs", dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    run_pipeline(
        image_path,
        out_dir,
        use_ocr_json=args.use_ocr_json,
        use_corrections_json=args.use_corrections,
        skip_ocr=args.skip_ocr,
        skip_openai=args.skip_openai,
    )


if __name__ == "__main__":
    main()
