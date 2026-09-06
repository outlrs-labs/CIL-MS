"""Load repository-owned subsidiary report contracts for both report paths."""
import json
from functools import lru_cache
from pathlib import Path

from .repository import OPERATING

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_ROOT = PROJECT_ROOT / 'report_templates' / 'subsidiaries'


@lru_cache(maxsize=64)
def load_report_template(entity: str, family: str) -> dict:
    """Return a validated prompt and family contract without accepting paths."""
    if entity not in OPERATING:
        return {'entity': entity, 'prompt': '', 'required_sections': [], 'parameters': []}
    folder = TEMPLATE_ROOT / entity
    try:
        contract = json.loads((folder / 'report.json').read_text(encoding='utf8'))
        prompt = (folder / 'prompt.md').read_text(encoding='utf8').strip()
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'Report template for {entity} is unavailable or invalid.') from exc
    if contract.get('subsidiary') != entity or contract.get('schema_version') != 1:
        raise RuntimeError(f'Report template for {entity} failed validation.')
    family_contract = contract.get('families', {}).get(family, {})
    return {
        'entity': entity,
        'prompt': prompt,
        'status': contract.get('status', 'draft'),
        'required_sections': list(contract.get('required_sections', [])),
        'parameters': list(family_contract.get('parameters', [])),
        'visuals': list(family_contract.get('visuals', contract.get('default_visuals', []))),
        'review_flow': contract.get('review_flow', {}),
    }


def analyst_instructions(entity: str, family: str) -> str:
    template = load_report_template(entity, family)
    if not template['prompt']:
        return ''
    contract = {
        'subsidiary': entity,
        'family': family,
        'required_sections': template['required_sections'],
        'parameters': template['parameters'],
        'visuals': template['visuals'],
        'review_flow': template['review_flow'],
    }
    return f"\nCIL report template:\n{template['prompt']}\nContract: {json.dumps(contract, separators=(',', ':'))}"
