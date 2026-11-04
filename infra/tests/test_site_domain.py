import pytest

from sound_along.config import parse_site_domain


def test_no_domain_means_the_cloudfront_address_only():
    assert parse_site_domain(None) is None


@pytest.mark.parametrize("value", ["sound-along.online", "Sound-Along.Online", "app.example.co.uk"])
def test_a_valid_hostname_is_accepted_and_lower_cased(value):
    assert parse_site_domain(value) == value.lower()


@pytest.mark.parametrize("value", ["", "localhost", "-bad.example.com", "bad-.example.com", "a..b.com", "https://sound-along.online", "sound along.online", "x" * 64 + ".com", 5, True])
def test_anything_else_is_refused(value):
    with pytest.raises(ValueError):
        parse_site_domain(value)


def test_every_setting_the_app_reads_reaches_the_pipeline_deploy():
    import pathlib
    import re

    from sound_along.config import PIPELINE_CONTEXT_KEYS

    source = (pathlib.Path(__file__).resolve().parent.parent / "app.py").read_text()
    read = set(re.findall(r'try_get_context\("([A-Za-z]+)"\)', source))
    passed_separately = {"ttsEngine", "cmsHost", "alertEmail"}  # passed on by their own flags
    pipeline_only = {"githubOwner", "githubRepo", "githubBranch"}  # settings of the pipeline stack itself
    assert read - passed_separately - pipeline_only - set(PIPELINE_CONTEXT_KEYS) == set()
