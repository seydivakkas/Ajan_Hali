"""
AI Confidence, Quality Scorer & Production Readiness Auditor
"""
import cv2
import numpy as np
from typing import List, Dict, Any
from core.models import ProductionAuditScore, YarnConsumptionItem


def evaluate_image_sharpness(image_rgb: np.ndarray) -> float:
    """Computes Laplacian variance as an indicator of focus and optical sharpness."""
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    # Normalize: variance > 300 is crisp, < 50 is blurry
    score = min(100.0, max(10.0, (laplacian_var / 300.0) * 100.0))
    return round(score, 1)


def audit_production_readiness(
    raw_image_rgb: np.ndarray,
    rect_metadata: Dict[str, Any],
    inpaint_metadata: Dict[str, Any],
    color_metrics: Dict[str, float],
    yarn_recipe: List[YarnConsumptionItem]
) -> ProductionAuditScore:
    """
    Computes holistic production readiness score (0-100) and categorizes into:
    READY | READY_WITH_WARNING | REVIEW_REQUIRED | NOT_PRODUCTION_SAFE.
    """
    sharpness_score = evaluate_image_sharpness(raw_image_rgb)
    rect_conf = rect_metadata.get("rectification_confidence", 0.7) * 100.0
    missing_pct = inpaint_metadata.get("missing_ratio_pct", 0.0)
    inpaint_conf = inpaint_metadata.get("mean_confidence", 1.0) * 100.0

    de_avg = color_metrics.get("delta_e_avg", 3.0)
    de_max = color_metrics.get("delta_e_max", 8.0)
    de_p95 = color_metrics.get("delta_e_p95", 5.0)

    # Color fidelity score: DeltaE = 0 -> 100, DeltaE = 10 -> 0
    color_fidelity = max(0.0, min(100.0, 100.0 - (de_avg * 10.0)))

    # Stock check
    stock_shortages = [item for item in yarn_recipe if not item.is_stock_sufficient]

    risk_flags = []
    recommendations = []

    if sharpness_score < 45.0:
        risk_flags.append("Düşük optik netlik / hareket bulanıklığı tespit edildi.")
        recommendations.append("Mümkünse tezgâha göndermeden önce daha yüksek çözünürlüklü veya tripodlu çekim yapın.")

    if rect_conf < 70.0:
        risk_flags.append("Yüksek perspektif açısı veya eğik çekim: köşe koordinatları yaklaşık tahmin edildi.")
        recommendations.append("CAD stüdyosunda bordür paralelliğini manuel cetvelle teyit edin.")

    if missing_pct > 12.0:
        risk_flags.append(f"Yüksek eksik alan oranı (%{missing_pct:.1f}): desenin önemli bölümü simetri ve AI ile tamamlandı.")
        recommendations.append("AI tamamlanan göbek ve bordür bölgelerini desinatör onayına sunun.")

    if de_avg > 4.5:
        risk_flags.append(f"Yüksek renk sapması (Ortalama DeltaE: {de_avg:.2f}): Fabrika paletinde tam eşleşmeyen ara tonlar var.")
        recommendations.append("Özellikle p95 DeltaE veren renkler için laboratuvar boyahanesinden alternatif bobin talep edin.")

    if stock_shortages:
        shortage_names = ", ".join([s.yarn_name for s in stock_shortages])
        risk_flags.append(f"Depo stok yetersizliği: {shortage_names} iplikleri siparişi karşılamıyor.")
        recommendations.append("Önerilen alternatif iplik kodlarını seçin veya hammadde satın alma emri açın.")

    # Calculate weighted overall score
    # 25% Image & Rectification + 25% Completion + 35% Color Fidelity + 15% Stock
    stock_score = 100.0 if not stock_shortages else max(40.0, 100.0 - len(stock_shortages) * 20.0)

    overall = (
        0.15 * sharpness_score +
        0.15 * rect_conf +
        0.20 * inpaint_conf +
        0.35 * color_fidelity +
        0.15 * stock_score
    )
    overall = round(max(0.0, min(100.0, overall)), 1)

    # Classify status
    if overall >= 82.0 and de_avg <= 3.2 and missing_pct <= 5.0 and not stock_shortages:
        status = "READY"
        recommendations.append("Tüm üretim kriterleri sağlandı. DXF ve jakar matrisi tezgâh operatörüne iletilebilir.")
    elif overall >= 68.0 and de_avg <= 5.2 and missing_pct <= 18.0:
        status = "READY_WITH_WARNING"
        recommendations.append("Üretim yapılabilir ancak belirtilen risk uyarıları vardiya şefi tarafından kontrol edilmelidir.")
    elif overall >= 45.0:
        status = "REVIEW_REQUIRED"
        recommendations.append("Üretime verilmeden önce desinatör revizyonu ve boyahane renk onayı ZORUNLUDUR.")
    else:
        status = "NOT_PRODUCTION_SAFE"
        recommendations.append("Halı görseli aşırı bozuk veya fabrikadaki mevcut paletle üretilemeyecek kadar farklı.")

    return ProductionAuditScore(
        overall_readiness_score=overall,
        input_quality_score=sharpness_score,
        segmentation_confidence=round(rect_conf, 1),
        completion_confidence=round(inpaint_conf, 1),
        color_fidelity_score=round(color_fidelity, 1),
        delta_e_avg=de_avg,
        delta_e_p95=de_p95,
        delta_e_max=de_max,
        status=status,
        risk_flags=risk_flags,
        technical_recommendations=recommendations
    )
