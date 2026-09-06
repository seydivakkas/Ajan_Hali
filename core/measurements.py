"""Import only explicit Lab triples; never invent measurements from missing fields."""
import math
import xml.etree.ElementTree as ET

def parse_explicit_lab(content, filename):
    samples = []
    def add(name, values):
        if not name or len(values) != 3:
            return
        try:
            lab = [float(v) for v in values]
            if not all(math.isfinite(v) for v in lab) or not 0 <= lab[0] <= 100 or any(abs(v) > 160 for v in lab[1:]):
                return
            samples.append({'name':name, 'lab':lab, 'source':'FILE_EXPLICIT_LAB', 'measurement_conditions':'UNVERIFIED'})
        except (ValueError,TypeError):
            return
    if filename.endswith('.qtx'):
        name = None
        for line in content.splitlines():
            if line.strip().startswith('NAME:'):
                name = line.split(':',1)[1].strip()
            elif line.strip().startswith('CIELAB:'):
                add(name, line.split(':',1)[1].split())
    else:
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return []
        for sample in root.iter():
            if sample.tag.split('}')[-1] not in {'ColorSample','Sample'}:
                continue
            name = sample.attrib.get('Name')
            for element in sample.iter():
                if element.tag.split('}')[-1] == 'CIELab':
                    values = {child.tag.split('}')[-1].upper():child.text for child in element.iter()}
                    add(name, [values.get(k) for k in ['L','A','B']])
                    break
    return samples
