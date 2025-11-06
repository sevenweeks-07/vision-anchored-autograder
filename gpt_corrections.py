#!/usr/bin/env python3
import argparse
import base64
import json
import mimetypes
import os
import re
from typing import Any, Dict, List

from config import (
    get_openai_client,
    openai_model_default,
    load_dotenv_if_available,
)


def encode_image_to_data_url(image_path: str) -> str:
    mime, _ = mimetypes.guess_type(image_path)
    if not mime:
        mime = "image/jpeg"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def extract_json_from_text(text: str) -> Dict[str, Any]:
    code_block = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    candidate = code_block.group(1) if code_block else None
    if not candidate:
        brace_match = re.search(r"(\{[\s\S]*\})", text)
        candidate = brace_match.group(1) if brace_match else None
    if not candidate:
        raise ValueError("No JSON object found in model response")
    cleaned = candidate.strip()
    return json.loads(cleaned)


def responses_text_output(resp) -> str:
    text = getattr(resp, "output_text", None)
    if text:
        return text
    parts: List[str] = []
    try:
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                t = getattr(c, "text", None)
                if t:
                    parts.append(t)
    except Exception:
        pass
    return "\n".join(parts) if parts else str(resp)


def get_corrections_from_prompt(prompt: str, image_path: str) -> Dict[str, Any]:
    load_dotenv_if_available()
    client = get_openai_client()
    model = openai_model_default()

    # Build multimodal input: prompt + image
    data_url = encode_image_to_data_url(image_path)
    input_payload = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": data_url},
            ],
        }
    ]

    try:
        resp = client.responses.create(
            model=model,
            input=input_payload,
            temperature=0.2,
            max_output_tokens=4096,
        )
    except Exception as e:
        # Common case: model does not support images (e.g., o3)
        raise RuntimeError(
            f"OpenAI call failed. Ensure the model supports images (e.g., gpt-4o, o4). Current model: {model}.\nOriginal error: {e}"
        )

    text = responses_text_output(resp)
    data = extract_json_from_text(text)

    if "corrections" not in data:
        raise ValueError("Model response missing 'corrections' array")
    if "overall_assessment" not in data:
        data["overall_assessment"] = {}

    return data


def main():
    ap = argparse.ArgumentParser(description="Call OpenAI (vision) to produce corrections JSON")
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--output-file", required=True)
    args = ap.parse_args()

    with open(args.prompt_file, "r", encoding="utf-8") as f:
        prompt = f.read()

    data = get_corrections_from_prompt(prompt, args.image)

    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Wrote corrections to {args.output_file}")


if __name__ == "__main__":
    main()
