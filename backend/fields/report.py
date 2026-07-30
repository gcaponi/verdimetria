"""Server-side A4 PDF agronomic report built from a completed AnalysisJob.

The report is a full document (not a page screenshot): cover, key metrics,
NDVI/NDMI series, terrain, land cover, AI interpretation, intervention log,
method and provenance. Extraction from the FieldAnalysis contract is fully
defensive: results produced by older pipeline versions may lack the optional
ndmi/variability/landCover blocks and must still render.
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")  # headless rendering: no display on the server

import matplotlib.pyplot as plt
from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.fields.models import AnalysisJob, Field, Intervention

BRAND = colors.HexColor("#4d7c0f")
INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#475569")
ROW_LINE = colors.HexColor("#e2e8f0")
BOX_BG = colors.HexColor("#f8fafc")

TONE_HEX = {"alert": "#be123c", "warn": "#b45309", "ok": "#047857", "info": "#0369a1"}
TONE_LABELS = {"alert": "Allerta", "warn": "Attenzione", "ok": "OK", "info": "Info"}

PAGE_WIDTH = A4[0]
CONTENT_WIDTH = PAGE_WIDTH - 4 * cm

_STYLES = {
    "brand": ParagraphStyle(
        "brand", fontName="Helvetica-Bold", fontSize=11, textColor=BRAND, spaceAfter=2
    ),
    "cover_title": ParagraphStyle(
        "cover_title", fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=INK
    ),
    "cover_field": ParagraphStyle(
        "cover_field", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=BRAND
    ),
    "h2": ParagraphStyle(
        "h2", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=INK,
        spaceBefore=16, spaceAfter=6,
    ),
    "h3": ParagraphStyle(
        "h3", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=INK,
        spaceBefore=10, spaceAfter=4,
    ),
    "body": ParagraphStyle(
        "body", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK
    ),
    "kv_label": ParagraphStyle(
        "kv_label", fontName="Helvetica", fontSize=9, leading=12, textColor=MUTED
    ),
    "kv_value": ParagraphStyle(
        "kv_value", fontName="Helvetica", fontSize=9, leading=12, textColor=INK
    ),
    "muted": ParagraphStyle(
        "muted", fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=MUTED
    ),
    "note": ParagraphStyle(
        "note", fontName="Helvetica-Oblique", fontSize=8, leading=11, textColor=MUTED
    ),
}

_MISSING = "n/d"


def cached_report_path(job: AnalysisJob) -> Path:
    """Disk cache file for the job report; the completed_at stamp invalidates
    the cache automatically when a retried job re-completes with a new result."""
    stamp = int(job.completed_at.timestamp()) if job.completed_at else 0
    return Path(settings.REPORT_CACHE_DIR) / f"{job.pk}-{stamp}.pdf"


def build_report_pdf(job: AnalysisJob) -> bytes:
    """Render the full agronomic report PDF for a completed job's result."""
    result = job.result if isinstance(job.result, dict) else {}
    field = job.field
    interventions = list(field.interventions.all())
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Report agronomico — {field.name}",
        author="Verdimetria",
    )
    story = _build_story(result, field, interventions)
    doc.build(story, onLaterPages=_footer)
    return buffer.getvalue()


def _build_story(
    result: dict[str, Any],
    field: Field,
    interventions: list[Intervention],
) -> list[Any]:
    story: list[Any] = []
    story.extend(_cover(result, field))
    story.append(PageBreak())
    story.extend(_sintesi(result))
    story.extend(_vegetazione(result))
    story.extend(_umidita(result))
    story.extend(_territorio(result))
    story.extend(_interpretazione(result))
    story.extend(_diario(interventions))
    story.extend(_metodo(result))
    return story


def _footer(canvas: Any, doc: Any) -> None:
    canvas.saveState()
    canvas.setStrokeColor(ROW_LINE)
    canvas.setLineWidth(0.5)
    canvas.line(2 * cm, 1.4 * cm, PAGE_WIDTH - 2 * cm, 1.4 * cm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(2 * cm, 1.0 * cm, "Verdimetria — report agronomico osservazionale da satellite")
    canvas.drawRightString(PAGE_WIDTH - 2 * cm, 1.0 * cm, f"Pagina {canvas.getPageNumber()}")
    canvas.restoreState()


# --- Sections ----------------------------------------------------------------


def _cover(result: dict[str, Any], field: Field) -> list[Any]:
    period = _record(result.get("period"))
    area = _record(result.get("area"))
    centroid = area.get("centroid")
    if isinstance(centroid, (list, tuple)) and len(centroid) == 2:
        centroid_text = f"{_fmt(centroid[0], 6)} / {_fmt(centroid[1], 6)} (lon/lat)"
    else:
        centroid_text = _MISSING
    rows = [
        ("Coltura dichiarata", _esc(field.crop) if field.crop else "Non dichiarata"),
        ("Data di generazione", _fmt_date(result.get("generatedAt"))),
        ("Periodo di analisi", f"{_fmt_date(period.get('from'))} – {_fmt_date(period.get('to'))}"),
        ("Superficie", _fmt_unit(area.get("hectares"), " ha", 2)),
        ("Centroide", centroid_text),
        ("ID analisi", _esc(result.get("analysisId") or _MISSING)),
    ]
    return [
        Spacer(1, 3 * cm),
        Paragraph("VERDIMETRIA", _STYLES["brand"]),
        HRFlowable(width="100%", thickness=1.5, color=BRAND, spaceAfter=10),
        Paragraph("Report agronomico di campo", _STYLES["cover_title"]),
        Spacer(1, 6),
        Paragraph(_esc(field.name), _STYLES["cover_field"]),
        Spacer(1, 1.2 * cm),
        _kv_table(rows),
    ]


def _sintesi(result: dict[str, Any]) -> list[Any]:
    vegetation = _record(result.get("vegetation"))
    ndmi = _record(result.get("ndmi"))
    variability = _record(result.get("variability"))
    terrain = _record(result.get("terrain"))
    elevation = _record(terrain.get("elevation"))
    slope = _record(terrain.get("slope"))
    catalog = _record(result.get("catalog"))
    rows: list[tuple[str, Any]] = [
        ("NDVI corrente", _fmt(vegetation.get("current"))),
        ("NDVI medio (periodo)", _fmt(vegetation.get("average"))),
        ("Trend NDVI (ultimi intervalli)", _fmt_signed(vegetation.get("trend"))),
        ("NDMI corrente", _fmt(ndmi.get("current")) if ndmi else _MISSING),
        (
            "Variabilita' di vigore (debole / intermedia / vigorosa)",
            (
                f"{_fmt(variability.get('weak'), 1)}% / {_fmt(variability.get('intermediate'), 1)}% "
                f"/ {_fmt(variability.get('vigorous'), 1)}%"
            )
            if variability
            else _MISSING,
        ),
        ("Pendenza media", _fmt_unit(slope.get("mean"), "°", 1)),
        ("Quota media", _fmt_unit(elevation.get("mean"), " m", 0)),
        ("Copertura dominante", _dominant_land_cover(result.get("landCover"))),
        ("Scene Sentinel-2", str(catalog.get("sceneCount") or _MISSING)),
        ("Osservazioni valide", str(vegetation.get("validObservations") or _MISSING)),
    ]
    return [
        Paragraph("Sintesi", _STYLES["h2"]),
        _kv_table(rows),
    ]


def _vegetazione(result: dict[str, Any]) -> list[Any]:
    vegetation = _record(result.get("vegetation"))
    variability = _record(result.get("variability"))
    story: list[Any] = [Paragraph("Vegetazione (NDVI)", _STYLES["h2"])]
    points = vegetation.get("points")
    chart = _ndvi_chart(points if isinstance(points, list) else [])
    if chart is not None:
        story.append(chart)
        story.append(Spacer(1, 8))
    story.append(_kv_table([
        ("NDVI corrente", _fmt(vegetation.get("current"))),
        ("NDVI medio (periodo)", _fmt(vegetation.get("average"))),
        ("NDVI minimo / massimo", f"{_fmt(vegetation.get('min'))} / {_fmt(vegetation.get('max'))}"),
        ("Trend NDVI (ultimi intervalli)", _fmt_signed(vegetation.get("trend"))),
        ("Osservazioni valide", str(vegetation.get("validObservations") or _MISSING)),
        ("Pixel validi totali", str(vegetation.get("totalValidPixels") or _MISSING)),
    ]))
    if not variability:
        story.append(Paragraph(
            "Variabilita' di vigore non disponibile per questa analisi.",
            _STYLES["muted"],
        ))
        return story
    thresholds = _record(variability.get("thresholds"))
    weak_max = _fmt(thresholds.get("weakMax"), 1)
    vigorous_min = _fmt(thresholds.get("vigorousMin"), 1)
    method = variability.get("method")
    method_note = (
        "Metodo: conteggio dei pixel reali dall'istogramma NDVI (Statistical API)."
        if method == "histogram"
        else "Metodo: stima approssimata da percentili (istogramma non disponibile)."
    )
    story.extend([
        Paragraph(
            f"Variabilita' di vigore — {_fmt_date(variability.get('date'))}",
            _STYLES["h3"],
        ),
        _kv_table([
            (f"Debole (NDVI < {weak_max})", f"{_fmt(variability.get('weak'), 1)}%"),
            (f"Intermedia ({weak_max}–{vigorous_min})", f"{_fmt(variability.get('intermediate'), 1)}%"),
            (f"Vigorosa (NDVI > {vigorous_min})", f"{_fmt(variability.get('vigorous'), 1)}%"),
            ("Pixel validi", str(variability.get("validPixels") or _MISSING)),
        ]),
        Spacer(1, 4),
        Paragraph(method_note, _STYLES["muted"]),
    ])
    note = variability.get("note")
    if isinstance(note, str) and note:
        story.append(Paragraph(_esc(note), _STYLES["note"]))
    return story


def _umidita(result: dict[str, Any]) -> list[Any]:
    ndmi = _record(result.get("ndmi"))
    story: list[Any] = [Paragraph("Umidita' della vegetazione (NDMI)", _STYLES["h2"])]
    if not ndmi:
        story.append(Paragraph(
            "Blocco NDMI non disponibile per questa analisi (formato precedente).",
            _STYLES["muted"],
        ))
        return story
    story.append(_kv_table([
        ("NDMI corrente", _fmt(ndmi.get("current"))),
        ("NDMI medio (periodo)", _fmt(ndmi.get("average"))),
        ("Trend NDMI (ultimi intervalli)", _fmt_signed(ndmi.get("trend"))),
    ]))
    current = ndmi.get("current")
    average = ndmi.get("average")
    if _is_number(current) and _is_number(average):
        position = "sopra" if current >= average else "sotto"
        text = (
            f"Il valore corrente ({_fmt(current)}) e' {position} la media del periodo "
            f"({_fmt(average)}). "
        )
    else:
        text = ""
    text += (
        "NDMI riflette il contenuto idrico della vegetazione: valori piu' alti indicano "
        "maggiore acqua nei tessuti. Confrontare sempre con l'andamento stagionale della coltura."
    )
    story.extend([Spacer(1, 4), Paragraph(text, _STYLES["body"])])
    return story


def _territorio(result: dict[str, Any]) -> list[Any]:
    terrain = _record(result.get("terrain"))
    elevation = _record(terrain.get("elevation"))
    slope = _record(terrain.get("slope"))
    story: list[Any] = [
        Paragraph("Territorio", _STYLES["h2"]),
        _kv_table([
            ("Quota minima / media / massima", (
                f"{_fmt(elevation.get('min'), 0)} / {_fmt(elevation.get('mean'), 0)} "
                f"/ {_fmt(elevation.get('max'), 0)} m"
            )),
            ("Pendenza media / massima", (
                f"{_fmt(slope.get('mean'), 1)}° / {_fmt(slope.get('max'), 1)}°"
            )),
            ("Esposizione dominante", str(terrain.get("aspectDominant") or _MISSING)),
            ("Risoluzione DEM", _fmt_unit(terrain.get("resolutionMeters"), " m", 0)),
            ("Fonte DEM", str(terrain.get("source") or "Copernicus DEM GLO-30")),
        ]),
    ]
    land_cover = _record(result.get("landCover"))
    classes = land_cover.get("classes") if land_cover else None
    if isinstance(classes, list) and classes:
        rows: list[list[Any]] = [[
            Paragraph("<b>Classe</b>", _STYLES["body"]),
            Paragraph("<b>Quota</b>", _STYLES["body"]),
            Paragraph("<b>Superficie</b>", _STYLES["body"]),
        ]]
        for entry in classes:
            if not isinstance(entry, dict):
                continue
            rows.append([
                Paragraph(_esc(entry.get("label") or _MISSING), _STYLES["body"]),
                _fmt_percent(entry.get("share")),
                _fmt_unit(entry.get("hectares"), " ha", 2),
            ])
        table = Table(rows, colWidths=[9 * cm, 4 * cm, 4 * cm], hAlign="LEFT")
        table.setStyle(_grid_style())
        story.extend([
            Paragraph(
                f"Copertura del suolo — CLC+ Backbone {land_cover.get('year', '')}",
                _STYLES["h3"],
            ),
            table,
            Spacer(1, 4),
            Paragraph(
                f"{_esc(land_cover.get('source') or 'CLC+ Backbone')} · "
                f"risoluzione {_fmt(land_cover.get('resolutionMeters'), 0)} m",
                _STYLES["muted"],
            ),
        ])
    return story


def _interpretazione(result: dict[str, Any]) -> list[Any]:
    ai = _record(result.get("ai"))
    status = ai.get("status")
    status_label = {
        "generated": "generata da AI",
        "fallback": "fallback basato su regole",
    }.get(str(status), str(status or _MISSING))
    story: list[Any] = [
        Paragraph("Interpretazione AI", _STYLES["h2"]),
        Paragraph(
            f"{_esc(ai.get('provider') or _MISSING)} · {_esc(ai.get('model') or _MISSING)} "
            f"· {status_label}",
            _STYLES["muted"],
        ),
        Spacer(1, 4),
    ]
    summary = ai.get("summary")
    if isinstance(summary, str) and summary:
        story.append(Paragraph(_esc(summary), _STYLES["body"]))
    insights = ai.get("insights")
    if not isinstance(insights, list) or not insights:
        story.append(Paragraph("Nessun insight disponibile.", _STYLES["muted"]))
        return story
    story.append(Spacer(1, 6))
    for insight in insights:
        if not isinstance(insight, dict):
            continue
        tone = str(insight.get("tone") or "info")
        tone_hex = TONE_HEX.get(tone, TONE_HEX["info"])
        tone_label = TONE_LABELS.get(tone, tone.upper())
        block = [
            Paragraph(
                f'<font color="{tone_hex}"><b>{tone_label}</b></font> — '
                f"<b>{_esc(insight.get('title') or '')}</b>",
                _STYLES["body"],
            ),
            Spacer(1, 2),
            Paragraph(_esc(insight.get("text") or ""), _STYLES["body"]),
        ]
        evidence = insight.get("evidence")
        if isinstance(evidence, str) and evidence:
            block.extend([
                Spacer(1, 2),
                Paragraph(f"Evidenza: {_esc(evidence)}", _STYLES["note"]),
            ])
        story.append(KeepTogether(block))
        story.append(Spacer(1, 8))
    return story


def _diario(interventions: list[Intervention]) -> list[Any]:
    story: list[Any] = [Paragraph("Diario degli interventi", _STYLES["h2"])]
    if not interventions:
        story.append(Paragraph("Nessun intervento registrato sul campo.", _STYLES["muted"]))
        return story
    rows: list[list[Any]] = [[
        Paragraph("<b>Data</b>", _STYLES["body"]),
        Paragraph("<b>Tipo</b>", _STYLES["body"]),
        Paragraph("<b>Note</b>", _STYLES["body"]),
    ]]
    for intervention in interventions:
        rows.append([
            intervention.date.strftime("%d/%m/%Y"),
            _esc(intervention.get_kind_display()),
            Paragraph(_esc(intervention.notes) if intervention.notes else "—", _STYLES["body"]),
        ])
    table = Table(rows, colWidths=[2.5 * cm, 4 * cm, 10.5 * cm], hAlign="LEFT", repeatRows=1)
    table.setStyle(_grid_style())
    story.append(table)
    return story


def _metodo(result: dict[str, Any]) -> list[Any]:
    story: list[Any] = [Paragraph("Metodo e provenance", _STYLES["h2"])]
    provenance = result.get("provenance")
    if isinstance(provenance, list):
        for entry in provenance:
            if not isinstance(entry, dict):
                continue
            services = entry.get("services")
            services_text = ", ".join(str(s) for s in services) if isinstance(services, list) else ""
            story.extend([
                Paragraph(
                    f"<b>{_esc(entry.get('provider') or _MISSING)}</b> — "
                    f"{_esc(entry.get('dataset') or '')}",
                    _STYLES["body"],
                ),
                Paragraph(
                    f"{_esc(services_text)} · {_esc(entry.get('quality') or '')}",
                    _STYLES["muted"],
                ),
                Spacer(1, 6),
            ])
    disclaimer = result.get("disclaimer")
    if isinstance(disclaimer, str) and disclaimer:
        box = Table(
            [[Paragraph(_esc(disclaimer), _STYLES["muted"])]],
            colWidths=[CONTENT_WIDTH],
            hAlign="LEFT",
        )
        box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BOX_BG),
            ("BOX", (0, 0), (-1, -1), 0.6, ROW_LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.extend([Spacer(1, 6), box])
    return story


# --- Chart and table helpers ---------------------------------------------------


def _ndvi_chart(points: list[Any]) -> Image | None:
    series = []
    for point in points:
        if not isinstance(point, dict):
            continue
        mean = point.get("mean")
        if not _is_number(mean):
            continue
        low = point.get("min")
        high = point.get("max")
        series.append((
            _short_date(point.get("date")),
            float(mean),
            float(low) if _is_number(low) else float(mean),
            float(high) if _is_number(high) else float(mean),
        ))
    if not series:
        return None
    xs = list(range(len(series)))
    labels = [row[0] for row in series]
    means = [row[1] for row in series]
    mins = [row[2] for row in series]
    maxs = [row[3] for row in series]
    fig_width, fig_height = 7.0, 2.6
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=200)
    try:
        ax.fill_between(xs, mins, maxs, color="#4d7c0f", alpha=0.15, linewidth=0)
        ax.plot(xs, means, color="#4d7c0f", marker="o", markersize=3.5, linewidth=1.4)
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=6.5)
        ax.set_ylabel("NDVI", fontsize=7)
        ax.tick_params(axis="y", labelsize=6.5)
        ax.grid(axis="y", alpha=0.25, linewidth=0.5)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        fig.tight_layout()
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png")
    finally:
        plt.close(fig)
    buffer.seek(0)
    return Image(buffer, width=16 * cm, height=16 * cm * fig_height / fig_width)


def _kv_table(rows: list[tuple[str, Any]]) -> Table:
    # Wrap plain strings in Paragraphs so long labels/values wrap instead of
    # overflowing the column (plain table strings are drawn on one line).
    wrapped = [
        (
            Paragraph(_esc(label), _STYLES["kv_label"]) if isinstance(label, str) else label,
            Paragraph(_esc(value), _STYLES["kv_value"]) if isinstance(value, str) else value,
        )
        for label, value in rows
    ]
    table = Table(wrapped, colWidths=[6.5 * cm, 10.5 * cm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, ROW_LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _grid_style() -> TableStyle:
    return TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEADING", (0, 0), (-1, -1), 12),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, ROW_LINE),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, MUTED),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])


def _dominant_land_cover(land_cover: Any) -> str:
    if not isinstance(land_cover, dict):
        return _MISSING
    classes = land_cover.get("classes")
    if not isinstance(classes, list) or not classes:
        return _MISSING
    entries = [entry for entry in classes if isinstance(entry, dict)]
    dominant_code = land_cover.get("dominantClass")
    dominant = next(
        (entry for entry in entries if entry.get("code") == dominant_code),
        None,
    )
    if dominant is None:
        dominant = max(entries, key=lambda entry: entry.get("share") or 0, default=None)
    if dominant is None:
        return _MISSING
    return f"{dominant.get('label') or _MISSING} ({_fmt_percent(dominant.get('share'))})"


# --- Formatting helpers --------------------------------------------------------


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _esc(value: Any) -> str:
    return escape(str(value))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _fmt(value: Any, digits: int = 3) -> str:
    if not _is_number(value):
        return _MISSING
    return f"{value:.{digits}f}".replace(".", ",")


def _fmt_signed(value: Any, digits: int = 3) -> str:
    if not _is_number(value):
        return _MISSING
    return f"{value:+.{digits}f}".replace(".", ",")


def _fmt_unit(value: Any, unit: str, digits: int = 1) -> str:
    text = _fmt(value, digits)
    return f"{text}{unit}" if text != _MISSING else text


def _fmt_percent(value: Any) -> str:
    """Share expressed as 0..1 -> percentage with Italian decimal comma."""
    if not _is_number(value):
        return _MISSING
    return f"{value * 100:.1f}%".replace(".", ",")


def _fmt_date(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return _MISSING
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return value[:10]


def _short_date(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    try:
        return datetime.fromisoformat(value[:10]).strftime("%d/%m")
    except ValueError:
        return value
