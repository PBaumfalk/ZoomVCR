from pathlib import Path
import yaml


def test_compose_is_structurally_valid_and_vnc_is_private():
    file = Path(__file__).resolve().parents[2] / 'compose.yml'
    compose = yaml.safe_load(file.read_text())
    assert {'desktop','postgres','redis','api','scheduler','capture','processor','web','proxy'} <= set(compose['services'])
    assert compose['services']['desktop']['ports'] == ['127.0.0.1:5900:5900']
    assert 'zoom_profile' in compose['volumes']
    assert 'zoom' in compose['services']['desktop']['profiles']
    assert 'desktop' not in compose['services']['proxy']['ports']
