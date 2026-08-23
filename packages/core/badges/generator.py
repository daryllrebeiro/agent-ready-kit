"""Dynamic vector SVG verification badge generator."""

from packages.core.schemas import Score

GRADE_COLORS = {
    "A+": "#10B981",
    "A": "#22C55E",
    "B": "#3B82F6",
    "C": "#F59E0B",
    "D": "#F97316",
    "F": "#EF4444",
}


class BadgeGenerator:
    """Renders pixel-perfect, accessible SVG badges for websites and GitHub READMEs."""

    @staticmethod
    def generate_svg(score: Score, label: str = "agent-ready") -> str:
        """Render SVG markup."""
        grade = score.grade
        score_val = f"{score.overall_score:.0f}"
        right_text = f"{grade} ({score_val}/100)"
        bg_color = GRADE_COLORS.get(grade, "#6B7280")

        # Dimensions
        left_width = 85
        right_width = max(80, len(right_text) * 9 + 16)
        total_width = left_width + right_width
        height = 20

        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" role="img" aria-label="{label}: {right_text}">
  <title>{label}: {right_text}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="{height}" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{left_width}" height="{height}" fill="#18181b"/>
    <rect x="{left_width}" width="{right_width}" height="{height}" fill="{bg_color}"/>
    <rect width="{total_width}" height="{height}" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
    <text aria-hidden="true" x="{left_width * 5}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{left_width * 8}">{label}</text>
    <text x="{left_width * 5}" y="140" transform="scale(.1)" fill="#fff" textLength="{left_width * 8}">{label}</text>
    <text aria-hidden="true" x="{(left_width + right_width / 2) * 10}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{right_width * 7}">{right_text}</text>
    <text x="{(left_width + right_width / 2) * 10}" y="140" transform="scale(.1)" fill="#fff" textLength="{right_width * 7}">{right_text}</text>
  </g>
</svg>"""
        return svg.strip()
