"""ReadWorks figures: found in order, tied to a paragraph, limited to ReadWorks' own host, fetched safely."""
import figures as fg

HOST = "https://dq5qica5h7eg3.cloudfront.net/CACHE/a.jpg"
HTML = (f'<p>One.</p><figure class="image"><img alt="a man" src="{HOST}"/><figcaption><div class="image-credit"><p>Jill L</p></div>'
        f'<div class="image-caption"><p>The new president.</p></div></figcaption></figure><p>Two.</p><p>Three.</p>'
        '<figure><img alt="x" src="https://evil.example/a.jpg"/></figure>')
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40


def test_figures_are_found_with_their_paragraph_caption_and_credit_and_foreign_hosts_are_dropped():
    found = fg.extract_figures(HTML)
    assert found == [fg.Figure(1, HOST, "a man", "The new president.", "Jill L")]


def test_an_empty_caption_is_allowed_and_paragraphs_inside_figures_are_not_counted():
    html = f'<figure><img alt="p" src="{HOST}"/><figcaption><div class="image-caption"><p> </p></div></figcaption></figure><p>A.</p>'
    (f,) = fg.extract_figures(html)
    assert f.after_paragraph == 0 and f.caption == ""


def test_fetch_keeps_real_images_only_and_never_raises():
    figs = [fg.Figure(0, HOST, "a", "cap", ""), fg.Figure(1, HOST + "2", "b", "", ""), fg.Figure(2, HOST + "3", "c", "", "")]
    replies = {HOST: JPEG, HOST + "2": b"<html>not an image</html>"}

    def get(url):
        if url not in replies:
            raise OSError("offline")
        return replies[url]

    entries, images = fg.fetch_figures("2b781dab-4521-40d2-a9b6-ad5f2bb0ba98", figs, get)
    assert len(entries) == 1 and entries[0]["afterParagraph"] == 0 and entries[0]["caption"] == "cap" and "credit" not in entries[0]
    (name,) = images
    assert name.startswith("2b781dab-4521-40d2-a9b6-ad5f2bb0ba98.figure-0-") and entries[0]["imageUrl"] == f"/data/{name}"
