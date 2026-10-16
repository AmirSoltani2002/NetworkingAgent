import math

import pytest

from rag.chunking import Chunker, structures
from rag.config import Settings
from tests.fakes import FakeEmbeddings


def test_semantic_splitter_is_used_within_sections(client):
    from llama_index.core.embeddings import BaseEmbedding
    from pydantic import PrivateAttr

    class FixtureEmbedding(BaseEmbedding):
        _fake = PrivateAttr(default_factory=FakeEmbeddings)

        def _get_text_embedding(self, text):
            return self._fake.texts([text])[0]

        def _get_query_embedding(self, query):
            return self._fake.query(query)

        async def _aget_query_embedding(self, query):
            return self._get_query_embedding(query)

    fixture = FakeEmbeddings()
    fixture.llama_model = FixtureEmbedding()
    settings = client.app.state.settings.model_copy(update={"semantic_min_chars": 100})
    sections = structures(
        [
            (
                None,
                "# Relays\n"
                + "Relay coils actuate contacts during startup. " * 12
                + "\n# Cooling\n"
                + "Cooling fans prevent motor overheating. " * 12,
            )
        ]
    )
    chunks = Chunker(settings, fixture).split(sections)
    assert {chunk.heading for chunk in chunks} == {"Relays", "Cooling"}
    assert all(chunk.metadata["chunking_method"] == "semantic_within_section" for chunk in chunks)
    assert all(fixture.token_count(chunk.content) <= fixture.max_tokens for chunk in chunks)


def test_page_provenance_and_warning_continuation(client, embeddings):
    pages = [
        (1, "# Troubleshooting\nWARNING: Disconnect power before inspection."),
        (
            2,
            "1. Inspect relay contacts.\n2. Replace worn components.\n\n"
            + "Carefully inspect contacts. " * 150,
        ),
    ]
    chunks = Chunker(client.app.state.settings, embeddings).split(structures(pages))
    assert chunks[0].page == 1
    continuation = [chunk for chunk in chunks if chunk.page == 2]
    assert continuation
    assert all("WARNING: Disconnect power" in chunk.content for chunk in continuation)
    assert all(chunk.metadata["page_numbers"] == [1, 2] for chunk in continuation)


@pytest.mark.model
def test_real_local_embeddings_semantic_chunking_and_no_generator(database):
    import importlib.util

    from rag.embeddings import LocalEmbeddings

    assert importlib.util.find_spec("openai") is None
    settings = Settings()
    model = LocalEmbeddings(settings)
    vectors = model.texts(
        [
            "Clicking relay during startup",
            "Relay clicking when powered on",
            "Bananas grow in tropical forests",
        ]
    )
    assert all(len(vector) == 384 for vector in vectors)
    assert all(abs(math.sqrt(sum(value * value for value in vector)) - 1) < 0.001 for vector in vectors)

    def cosine(left, right):
        return sum(a * b for a, b in zip(left, right))

    assert cosine(vectors[0], vectors[1]) > cosine(vectors[0], vectors[2])
    settings = settings.model_copy(update={"semantic_min_chars": 100})
    source = "# Relay Inspection\n" + "Relay contact wear can cause clicking during startup. " * 40
    chunks = Chunker(settings, model).split(structures([(3, source)]))
    assert chunks and all(chunk.heading == "Relay Inspection" and chunk.page == 3 for chunk in chunks)
    assert all(model.token_count(chunk.content) <= model.max_tokens for chunk in chunks)
    # Token bounding preserves original case/content, rather than tokenizer-decoded approximations.
    original = "Mixed CASE source text and punctuation! " * 100
    assert all(part in original for part in model.token_parts(original))


@pytest.mark.model
def test_real_optional_local_cross_encoder(database):
    from rag.embeddings import LocalReranker

    model = LocalReranker(Settings())
    scores = model.scores(
        "relay clicking during startup",
        ["Relay contacts may be worn during startup.", "Bananas grow in tropical forests."],
    )
    assert len(scores) == 2 and scores[0] > scores[1]
