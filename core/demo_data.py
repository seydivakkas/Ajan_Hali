"""Explicitly synthetic training inventory; never represents supplier measurements."""
from core.factory_settings import YarnSettings, load_settings, save_settings


def demo_yarns():
    samples = [('CREAM', 'Krem Ekru', [85, 2, 12], 120, 80),
               ('GREY', 'Vizon Gri', [55, 1, 3], 135, 60),
               ('NAVY', 'Koyu Lacivert', [25, 5, -20], 145, 40),
               ('RED', 'Bordo', [35, 35, 10], 150, 0.1)]
    return [YarnSettings(code=f'DEMO_{code}', name=name, material='PP Heatset BCF',
                         dtex=1800, rgb=(0, 0, 0), lab=lab, color_source='DEMO_SYNTHETIC',
                         is_demo=True, cost_per_kg_tl=price, stock_kg=stock, bobbin_weight_kg=5)
            for code, name, lab, price, stock in samples]


def change_demo_inventory(revision: int, remove: bool = False):
    settings = load_settings()
    if settings.revision != revision:
        raise ValueError('Ayarlar değişti. Sayfayı yenileyip tekrar deneyin.')
    if remove:
        settings.yarns = [y for y in settings.yarns if not y.is_demo]
    elif not any(y.is_demo for y in settings.yarns):
        incoming = demo_yarns()
        if {y.code.casefold() for y in settings.yarns} & {y.code.casefold() for y in incoming}:
            raise ValueError('DEMO stok kodları mevcut kayıtlarda kullanılıyor; hiçbir kayıt değişmedi.')
        settings.yarns += incoming
    else:
        return settings
    return save_settings(settings)


def mark_demo_result(result, yarns):
    result.data_source = 'DEMO_SYNTHETIC' if any(y.is_demo for y in yarns) else 'USER_FACTORY_INPUT'
    if result.data_source == 'DEMO_SYNTHETIC':
        result.audit.status = 'NOT_PRODUCTION_SAFE'
        result.audit.risk_flags.append('DEMO — Sentetik iplik, renk ve maliyet verileri; üretimde kullanmayın.')
        result.production_audit = result.audit
    return result
