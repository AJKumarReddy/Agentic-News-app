"""Publisher names in the evidence labels the model reads.

The defect: TheNewsAPI reports each relayed newsroom by domain, that domain
went into the evidence label verbatim, and the model wrote it back into prose
as "according to foxnews.com".
"""

from app.agents.graph import _format_entry
from app.sources.publishers import publisher_name


class TestPublisherName:
    def test_maps_known_domains_to_the_newsroom_name(self):
        assert publisher_name("nypost.com") == "NY Post"
        assert publisher_name("cbsnews.com") == "CBS News"
        assert publisher_name("foxnews.com") == "FOX News"
        assert publisher_name("abcnews.go.com") == "ABC News"
        assert publisher_name("bbc.co.uk") == "BBC News"

    def test_normalises_protocol_www_and_path(self):
        assert publisher_name("https://www.nypost.com/") == "NY Post"
        assert publisher_name("WWW.CBSNEWS.COM") == "CBS News"

    def test_tidies_domains_it_has_no_curated_name_for(self):
        assert publisher_name("sfgate.com") == "Sfgate"
        assert publisher_name("some-local-paper.co.uk") == "Some Local Paper"

    def test_leaves_real_publisher_names_untouched(self):
        assert publisher_name("The Guardian") == "The Guardian"
        assert publisher_name("The New York Times") == "The New York Times"

    def test_handles_empty_input(self):
        assert publisher_name("") == ""
        assert publisher_name(None) == ""


class TestEvidenceLabel:
    def _entry(self, **overrides):
        item = {
            "n": 1,
            "type": "publisher",
            "source": "foxnews.com",
            "group": "default",
            "headline": "Something happened",
            "published_at": "2026-08-21T09:00:00Z",
            "text": "Body text.",
        }
        item.update(overrides)
        return _format_entry(item)

    def test_labels_the_newsroom_not_the_domain(self):
        entry = self._entry()
        assert "FOX News" in entry
        assert "foxnews.com" not in entry

    def test_web_sources_are_named_too(self):
        entry = self._entry(type="web", source="cbsnews.com")
        assert "CBS News" in entry
        assert "cbsnews.com" not in entry

    def test_publishers_that_already_send_a_name_are_unchanged(self):
        assert "The New York Times" in self._entry(source="The New York Times")

    def test_falls_back_when_no_source_is_given(self):
        assert "The Guardian" in self._entry(source="")
        assert "web" in self._entry(type="web", source="")

    def test_keeps_the_citation_number_and_date(self):
        entry = self._entry()
        assert entry.startswith("[1] Something happened (2026-08-21, FOX News)")
