#!/usr/bin/env python3
"""Generate Shimeji/Shijima mascot assets using the xAI Grok API.

This script is **offline tooling only**: you run it manually to build
frames and XML for a new mascot pack. It is not used at runtime by
niodoo-shimeji.

Requirements:
- Python 3.10+
- Option A: `xai-sdk` for talking to the Grok API (image mode)
- Option B: `opencv-python` for extracting frames from your own videos (video mode)

Usage (video mode – recommended for Grok web workflows):
    # Place your videos under Shijima-Qt/Mascots/<MascotName>/ as .mp4 files
    python tools/generate_shimeji_assets.py \
        --mascot-name "TestMascot1" \
        --video-mode

Usage (image-only mode – uses xAI API directly):
    export XAI_API_KEY=sk-...
    python tools/generate_shimeji_assets.py \
        --description "a playful fox that explores desktops" \
        --mascot-name "FoxMascot"

The script will create (both modes):
    Shijima-Qt/Mascots/<MascotName>/img/<MascotName>/shime1.png..shime46.png
    Shijima-Qt/Mascots/<MascotName>/conf/actions.xml
    Shijima-Qt/Mascots/<MascotName>/conf/behaviors.xml
"""

from __future__ import annotations

import argparse
import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

try:
    from xai_sdk import Client  # type: ignore
except ImportError:  # pragma: no cover - guidance only
    Client = None  # type: ignore

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover
    cv2 = None


# Canonical 46-frame layout and action mapping, aligned with your repo.
# Each entry maps an action name to an inclusive frame range within 1..46.
BASELINE_ACTIONS: Dict[str, Tuple[int, int]] = {
    "Stand": (1, 6),  # idle/stand loop
    "Walk": (7, 14),  # walking cycle
    "Run": (15, 22),  # running/dash cycle
    "Sit": (23, 28),
    "SitDown": (23, 28),
    "Sprawl": (23, 28),
    "SitAndFaceMouse": (29, 30),
    "SitAndLookAtMouse": (29, 30),
    "Jump": (31, 36),
    "Jumping": (31, 36),
    "Fall": (37, 40),
    "ClimbWall": (41, 46),
    "GrabWall": (41, 46),
    "ClimbIEWall": (41, 46),
    "ChaseMouse": (15, 22),  # alias of Run
}


@dataclass
class GenerationConfig:
    description: str | None
    mascot_name: str
    root_dir: Path
    model: str = "grok-2-image"

    @property
    def img_dir(self) -> Path:
        return self.root_dir / "img" / self.mascot_name

    @property
    def conf_dir(self) -> Path:
        return self.root_dir / "conf"


def _ensure_dirs(cfg: GenerationConfig) -> None:
    cfg.img_dir.mkdir(parents=True, exist_ok=True)
    cfg.conf_dir.mkdir(parents=True, exist_ok=True)


def _build_frame_prompts(cfg: GenerationConfig) -> Dict[int, str]:
    """Build a prompt per frame index (1..46) based on owning action.

    We assign each frame a primary action whose visual pose should be
    represented. Where multiple actions share a frame range (aliases like
    Jump/Jumping), we pick a canonical one for the prompt text.
    """

    # Canonical action label per frame
    frame_action: Dict[int, str] = {}

    # Pick canonical actions first (no aliases) in priority order
    canonical_order = [
        "Stand",
        "Walk",
        "Run",
        "Sit",
        "Sprawl",
        "SitAndFaceMouse",
        "SitAndLookAtMouse",
        "Jump",
        "Fall",
        "ClimbWall",
    ]
    alias_map = {
        "SitDown": "Sit",
        "Jumping": "Jump",
        "GrabWall": "ClimbWall",
        "ClimbIEWall": "ClimbWall",
        "ChaseMouse": "Run",
    }

    for action in canonical_order:
        start, end = BASELINE_ACTIONS[action]
        for frame in range(start, end + 1):
            frame_action.setdefault(frame, action)

    # Fill any remaining holes defensively (should not happen with 1..46)
    for frame in range(1, 47):
        frame_action.setdefault(frame, "Stand")

    if not cfg.description:
        raise SystemExit("Image generation mode requires --description.")

    prompts: Dict[int, str] = {}
    for frame, action in frame_action.items():
        # Basic English description for the pose
        if action == "Stand":
            pose = "standing idle with a relaxed expression"
        elif action == "Walk":
            pose = "mid-walk, one foot forward, casual movement"
        elif action == "Run":
            pose = "running quickly, energetic motion"
        elif action in {"Sit", "Sprawl"}:
            pose = "sitting or lounging comfortably"
        elif action == "SitAndFaceMouse":
            pose = "sitting, looking slightly to the side as if at the cursor"
        elif action == "SitAndLookAtMouse":
            pose = "sitting, eyes tracking something on the screen"
        elif action == "Jump":
            pose = "in mid-jump, excited and bouncy"
        elif action == "Fall":
            pose = "falling downward in a playful, surprised way"
        elif action == "ClimbWall":
            pose = "climbing a vertical surface, hands and feet gripping"
        else:
            pose = "in a neutral mascot pose"

        prompts[frame] = (
            f"{cfg.description}, Shimeji-style desktop mascot, {pose}, "
            "clean 2D sprite, consistent style, transparent background"
        )

    return prompts


def _decode_image_data(response) -> bytes:
    """Decode image bytes from xAI response.

    We assume the client returns an object with either raw bytes or base64.
    This is a small shim so the script can be adjusted once you confirm the
    exact `xai-sdk` response shape.
    """

    # Placeholder: adjust based on actual xai-sdk return type.
    # Example if response.image is base64 string:
    data = getattr(response, "image", None)
    if isinstance(data, str):
        try:
            return base64.b64decode(data)
        except Exception:
            pass
    # If the SDK already returns raw bytes, just return them.
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    raise RuntimeError("Unexpected image data format from xAI response; adjust _decode_image_data().")


def generate_images(cfg: GenerationConfig) -> None:
    if not cfg.description:
        raise SystemExit("Image generation mode requires --description.")

    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise SystemExit("XAI_API_KEY environment variable is not set.")

    if Client is None:
        raise SystemExit("xai-sdk is not installed. Run: pip install xai-sdk")

    client = Client(api_key=api_key)

    _ensure_dirs(cfg)
    prompts = _build_frame_prompts(cfg)

    for frame in range(1, 47):
        prompt = prompts[frame]
        print(f"[xAI] Generating frame {frame}/46: {prompt}")
        # Adjust this call once you know the exact xai-sdk signature.
        response = client.image.sample(
            model=cfg.model,
            prompt=prompt,
            image_format="base64",  # or appropriate flag per SDK
        )
        img_bytes = _decode_image_data(response)
        out_path = cfg.img_dir / f"shime{frame}.png"
        with out_path.open("wb") as f:
            f.write(img_bytes)

    print(f"Generated 46 frames in {cfg.img_dir}")


def _extract_frames_from_video(video_path: Path, num_frames: int) -> list:
    """Extract approximately num_frames evenly spaced frames from a video file."""

    if cv2 is None:
        raise SystemExit("opencv-python is not installed. Run: pip install opencv-python")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    if frame_count == 0:
        cap.release()
        raise RuntimeError(f"Video has no frames: {video_path}")

    # Compute indices to sample approximately evenly across the clip.
    indices = [int(i * frame_count / num_frames) for i in range(num_frames)]

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        frames.append(frame)

    cap.release()
    return frames


def _make_background_transparent(frame, *, sample_margin: int = 4, threshold: int = 10):
    """Return an RGBA frame with the background color made transparent.

    We sample a few pixels from the corners to estimate the background color,
    then zero out alpha for pixels within `threshold` of that color.
    """

    import numpy as np

    if frame is None:
        return frame

    # Frame is BGR from OpenCV
    h, w, _ = frame.shape
    margin = sample_margin
    corners = [
        frame[margin, margin],
        frame[margin, w - margin - 1],
        frame[h - margin - 1, margin],
        frame[h - margin - 1, w - margin - 1],
    ]
    bg_color = np.mean(np.array(corners, dtype=np.float32), axis=0)  # BGR

    # Convert to float for distance calc
    bgr = frame.astype(np.float32)
    diff = np.linalg.norm(bgr - bg_color, axis=2)

    # Build alpha mask: 0 where close to bg_color, 255 otherwise
    alpha = np.where(diff <= threshold, 0, 255).astype(np.uint8)

    # Convert BGR to BGRA with our alpha
    b, g, r = cv2.split(frame)
    rgba = cv2.merge((b, g, r, alpha))
    return rgba


def generate_from_videos(cfg: GenerationConfig) -> None:
    """Generate shime1..shime46.png from pre-made behavior videos.

    This mode assumes you've already created videos in:
        root_dir/<MascotName>/
    with specific filenames, for example under:
        Shijima-Qt/Mascots/TestMascot1/
    """

    if cv2 is None:
        raise SystemExit("opencv-python is not installed. Run: pip install opencv-python")

    _ensure_dirs(cfg)

    # Video filenames relative to the mascot root directory.
    mascot_root = cfg.root_dir / cfg.mascot_name
    video_map = {
        "Stand": mascot_root / "Idle.mp4",
        "Walk": mascot_root / "WalkingRight.mp4",
        "Run": mascot_root / "Runningtotheright.mp4",
        "Sit": mascot_root / "Sittingarmscrossed.mp4",
        "Sprawl": mascot_root / "Spawl.mp4",
        "SitAndLookAtMouse": mascot_root / "curiouslookingrighttoleft.mp4",
        "Jump": mascot_root / "Jump.mp4",
        "Fall": mascot_root / "Falling.mp4",
        "ClimbWall": mascot_root / "Climbing.mp4",
        # Optional extras
        "Creep": mascot_root / "Creeprightthenleft.mp4",
        "Bouncing": mascot_root / "Bouncing.mp4",
    }

    # Mapping from actions to frame ranges we want to fill.
    frame_layout: Dict[str, Tuple[int, int]] = {
        "Stand": (1, 6),
        "Walk": (7, 14),
        "Run": (15, 22),  # also used by Dash/ChaseMouse
        "Sit": (23, 28),  # also SitDown/Sprawl
        "SitAndLookAtMouse": (29, 30),  # also SitAndFaceMouse
        "Jump": (31, 36),  # also Jumping
        "Fall": (37, 40),
        "ClimbWall": (41, 46),  # also GrabWall/ClimbIEWall
    }

    # For each action, sample frames from the corresponding video and save.
    for action, (start, end) in frame_layout.items():
        video_path = video_map[action]
        if not video_path.exists():
            raise SystemExit(f"Expected video not found for action '{action}': {video_path}")

        num_needed = end - start + 1
        print(f"[video] Extracting {num_needed} frames for {action} from {video_path}")
        frames = _extract_frames_from_video(video_path, num_needed)
        if len(frames) < num_needed:
            print(
                f"Warning: extracted {len(frames)} frames for {action}, "
                f"but {num_needed} were requested; some frames will be repeated."
            )
        # Write frames into the shime slots
        for offset, frame_idx in enumerate(range(start, end + 1)):
            src_idx = min(offset, len(frames) - 1)
            frame = frames[src_idx]
            frame = _make_background_transparent(frame)
            out_path = cfg.img_dir / f"shime{frame_idx}.png"
            # Ensure directory exists
            cfg.img_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out_path), frame)

    print(f"Generated 46 frames from videos into {cfg.img_dir}")


def generate_actions_xml(cfg: GenerationConfig) -> None:
    import xml.etree.ElementTree as ET

    root = ET.Element("Actions")

    # Deduplicate actions but preserve ordering of insertion
    seen = set()
    for action, (start, end) in BASELINE_ACTIONS.items():
        canonical = action
        if canonical in seen:
            continue
        seen.add(canonical)
        act_elem = ET.SubElement(root, "Action", Name=canonical)
        for i in range(start, end + 1):
            ET.SubElement(act_elem, "Pose", Image=f"/shime{i}.png", Duration="100")

    tree = ET.ElementTree(root)
    cfg.conf_dir.mkdir(parents=True, exist_ok=True)
    out_path = cfg.conf_dir / "actions.xml"
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"Wrote actions.xml to {out_path}")


def generate_behaviors_xml(cfg: GenerationConfig) -> None:
    import xml.etree.ElementTree as ET

    root = ET.Element("Behaviors")

    # Simple baseline behaviors referencing existing actions.
    ET.SubElement(root, "Behavior", Action="Walk", Frequency="0.5")
    ET.SubElement(root, "Behavior", Action="Stand", Frequency="0.3")
    ET.SubElement(root, "Behavior", Action="Sit", Frequency="0.1")
    ET.SubElement(root, "Behavior", Action="Jump", Frequency="0.1")
    ET.SubElement(root, "Behavior", Action="Fall", Frequency="0.0", Trigger="External")

    tree = ET.ElementTree(root)
    cfg.conf_dir.mkdir(parents=True, exist_ok=True)
    out_path = cfg.conf_dir / "behaviors.xml"
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"Wrote behaviors.xml to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Shimeji assets (image or video mode)")
    parser.add_argument("--description", help="Mascot description, e.g. 'a curious fox' (image mode only)")
    parser.add_argument("--mascot-name", required=True, help="Mascot name/folder, e.g. 'FoxMascot'")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "Shijima-Qt" / "Mascots",
        help="Root directory where the mascot pack will be created (default: Shijima-Qt/Mascots)",
    )
    parser.add_argument(
        "--model",
        default="grok-2-image",
        help="xAI image model name (default: grok-2-image; image mode only)",
    )
    parser.add_argument(
        "--video-mode",
        action="store_true",
        help="Use pre-rendered videos under <root>/<mascot-name>/ instead of calling xAI",
    )

    args = parser.parse_args()

    cfg = GenerationConfig(
        description=args.description,
        mascot_name=args.mascot_name,
        root_dir=args.root,
        model=args.model,
    )

    if args.video_mode:
        print(f"Generating mascot '{cfg.mascot_name}' from videos under {cfg.root_dir}/{cfg.mascot_name}")
        generate_from_videos(cfg)
    else:
        print(f"Generating mascot '{cfg.mascot_name}' into {cfg.root_dir} using model {cfg.model}")
        generate_images(cfg)

    generate_actions_xml(cfg)
    generate_behaviors_xml(cfg)
    print("Done. Copy or load this mascot in Shijima-Qt as usual.")


if __name__ == "__main__":  # pragma: no cover
    main()
