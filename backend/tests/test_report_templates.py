from pathlib import Path

from app.config import Settings
from app.integration.report_templates import TEMPLATE_ROOT, analyst_instructions, load_report_template
from app.integration.repository import OPERATING


def test_default_storage_stays_inside_project():
    configured = Settings(_env_file=None)
    project = Path(__file__).resolve().parents[2]
    assert configured.cil_data_root == project / 'Data' / 'cil'
    assert configured.cil_processing_root == project / 'Data' / '.processing'


def test_every_subsidiary_has_a_valid_two_file_report_contract():
    for entity in OPERATING:
        folder = TEMPLATE_ROOT / entity
        assert {path.name for path in folder.iterdir()} == {'prompt.md', 'report.json'}
        template = load_report_template(entity, 'production_offtake')
        assert template['entity'] == entity
        assert template['parameters'] == ['Production', 'Off-take', 'Dispatch', 'Stock balance']
        assert template['review_flow']['destination'] == 'CMPDI'
        instructions = analyst_instructions(entity, 'production_offtake')
        assert entity in instructions
        assert 'required_sections' in instructions
