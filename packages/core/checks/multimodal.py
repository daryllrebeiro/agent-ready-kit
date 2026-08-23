"""Multimodal content and visual agent readiness evaluation."""

from typing import Any, Dict, List
from bs4 import BeautifulSoup
from packages.core.checks.structured_data import extract_json_ld
from packages.core.schemas import ComponentStatus, ScoreComponent

GENERIC_ALT_TEXTS = {"image", "photo", "img", "untitled", "picture", "graphic", "logo.png", "image.png", "icon"}


def check_multimodal(
    html: str,
    weight: float = 0.15,
) -> ScoreComponent:
    """Evaluate image alt descriptions, video metadata, and visual entity grounding."""
    recommendations: List[str] = []
    evidence: Dict[str, Any] = {
        "total_images": 0,
        "images_with_descriptive_alt": 0,
        "images_missing_alt": 0,
        "video_objects_detected": 0,
        "has_og_image": False,
    }

    if not html or not html.strip():
        return ScoreComponent(
            name="multimodal_readiness",
            display_name="Multimodal Visual & Media Readiness",
            score=0.0,
            weight=weight,
            status=ComponentStatus.FAIL,
            evidence=evidence,
            details="Empty document provided.",
            recommendations=["Include descriptive image alt text and structured video metadata."],
        )

    soup = BeautifulSoup(html, "html.parser")
    json_ld = extract_json_ld(soup)

    # 1. Image Alt Text Audit
    images = soup.find_all("img")
    evidence["total_images"] = len(images)

    descriptive_alt_count = 0
    missing_alt_count = 0

    for img in images:
        alt = img.get("alt", "").strip()
        if not alt:
            missing_alt_count += 1
        elif alt.lower() in GENERIC_ALT_TEXTS or len(alt) < 4:
            missing_alt_count += 1
        else:
            descriptive_alt_count += 1

    evidence["images_with_descriptive_alt"] = descriptive_alt_count
    evidence["images_missing_alt"] = missing_alt_count

    # 2. Video / Media Metadata
    types = [str(b.get("@type", "")) for b in json_ld]
    video_count = sum(1 for t in types if "VideoObject" in t or "AudioObject" in t)
    evidence["video_objects_detected"] = video_count

    # 3. OpenGraph Visuals
    og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
    evidence["has_og_image"] = bool(og_img and og_img.get("content"))

    # Scoring calculation
    score = 0.0

    # Image Alt Quality (Max 50 pts)
    if len(images) == 0:
        score += 35.0  # Clean text site
    else:
        alt_ratio = descriptive_alt_count / len(images)
        score += alt_ratio * 50.0
        if alt_ratio < 0.7:
            recommendations.append(f"Add descriptive `alt` text to {missing_alt_count} images for vision-capable AI models.")

    # Video Schema (Max 25 pts)
    if video_count > 0:
        score += 25.0
    elif soup.find(["video", "iframe"]):
        score += 10.0
        recommendations.append("Wrap embedded videos with Schema.org `VideoObject` metadata (name, description, uploadDate, transcript).")
    else:
        score += 25.0  # Not a video-dependent page

    # OpenGraph Image (Max 25 pts)
    if evidence["has_og_image"]:
        score += 25.0
    else:
        recommendations.append("Define `<meta property=\"og:image\" content=\"...\">` to ensure visual brand previews for chat agents.")

    score = min(100.0, max(0.0, score))

    if score >= 80.0:
        status = ComponentStatus.PASS
        details = f"Strong multimodal readiness: {descriptive_alt_count}/{len(images)} images have descriptive alt text with valid OpenGraph previews."
    elif score >= 50.0:
        status = ComponentStatus.WARN
        details = f"Moderate multimodal accessibility: {missing_alt_count} images lack descriptive alt text."
    else:
        status = ComponentStatus.FAIL
        details = "Poor multimodal readiness. Visual elements lack semantic descriptions."

    return ScoreComponent(
        name="multimodal_readiness",
        display_name="Multimodal Visual & Media Readiness",
        score=round(score, 1),
        weight=weight,
        status=status,
        evidence=evidence,
        details=details,
        recommendations=recommendations,
    )
