"""Analyze a supplied photograph with explicitly supplied factory parameters."""
import argparse
import json
import os
from pathlib import Path
from core.models import LoomConfig, ImagePreprocessingParams
from core.pipeline import CarpetAnalysisPipeline
from core.factory_settings import load_settings
from core.supplier_catalog import validate_matching_conditions
from core.demo_data import mark_demo_result


def main():
    parser = argparse.ArgumentParser(description='Ajan Halı: gerçek fotoğraf ve kayıtlı şirket paletiyle analiz')
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path, help='loom_config ve isteğe bağlı preprocessing_config içeren JSON')
    args = parser.parse_args()
    settings = load_settings()
    if not settings.yarns or (not settings.company_name and not any(y.is_demo for y in settings.yarns)):
        parser.error('Önce stüdyoda Fabrika Ayarları bölümünü tamamlayın.')
    validate_matching_conditions(settings.yarns)
    data = json.loads(args.config.read_text(encoding='utf-8'))
    values = data.get('loom_config', {})
    required = {'width_cm','length_cm','reed_density','pick_density','pile_height_mm','max_colors','order_quantity','waste_coefficient','weave_structure_factor','anchor_length_mm'}
    if required - values.keys():
        parser.error('Eksik üretim parametreleri: ' + ', '.join(sorted(required - values.keys())))
    output = Path(__file__).resolve().parent / 'output'
    worker = CarpetAnalysisPipeline(output_base_dir=str(output), palette=[y.model_dump() for y in settings.yarns])
    result = worker.process(str(args.image), LoomConfig(**values), ImagePreprocessingParams(**data.get('preprocessing_config', {})))
    mark_demo_result(result, settings.yarns)
    result.factory_settings_revision = settings.revision
    result.company_name = settings.company_name
    path = output / result.job_id / 'analysis_report.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(result.model_dump_json(indent=2),encoding='utf-8')
    os.replace(temporary,path)
    print(f'Analiz: {result.job_id}\nRapor: {path}\nTahmini iplik maliyeti: {result.total_order_cost_tl:.2f} TL')

if __name__ == '__main__':
    main()
