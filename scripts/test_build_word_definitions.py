import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_word_definitions as b

LMF = b"""<?xml version="1.0"?><LexicalResource><Lexicon id="oewn" label="x" language="en" email="e" license="l" version="1" url="u">
<LexicalEntry id="e1"><Lemma writtenForm="elephant" partOfSpeech="n"><Pronunciation variety="US">ELI</Pronunciation></Lemma><Sense id="s1" synset="y1"/></LexicalEntry>
<LexicalEntry id="e2"><Lemma writtenForm="Paris" partOfSpeech="n"/><Sense id="s2" synset="y1"/></LexicalEntry>
<LexicalEntry id="e3"><Lemma writtenForm="ice cream" partOfSpeech="n"/><Sense id="s3" synset="y1"/></LexicalEntry>
<LexicalEntry id="e4"><Lemma writtenForm="big" partOfSpeech="s"/><Sense id="s4" synset="y2"/><Sense id="s5" synset="y1"/></LexicalEntry>
<Synset id="y1" partOfSpeech="n"><Definition>a large animal; with a trunk</Definition><Example>The elephant ate.</Example></Synset>
<Synset id="y2" partOfSpeech="a"><Definition>of great size</Definition></Synset>
</Lexicon></LexicalResource>"""


def test_only_single_lowercase_words_with_the_first_sense_per_part_of_speech():
    t = b.parse_wordnet(io.BytesIO(LMF))
    assert t["elephant"] == {"n": [["a large animal", "The elephant ate.", "ELI"]]}
    assert "Paris" not in t and "ice cream" not in t
    assert t["big"] == {"a": [["of great size", "", ""], ["a large animal", "The elephant ate.", ""]]}
