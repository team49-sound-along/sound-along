import pytest

from engines import create_engine


def test_unknown_engine_is_rejected_with_a_clear_message():
    with pytest.raises(ValueError, match="Use 'kokoro', 'phonon' or 'polly'"):
        create_engine("espeak")
