from content.knowledge_map import get_knowledge_nodes


def test_knowledge_map_has_core_topics():
    titles = {node.title for node in get_knowledge_nodes()}

    assert "Discounted Cash Flow Valuation" in titles
    assert "Dynamic DCF Default Derivation" in titles
    assert "Financial Health / Piotroski-Style Score" in titles
    assert "Quality vs Value Screener" in titles


def test_knowledge_map_nodes_are_complete_and_sourced():
    for node in get_knowledge_nodes():
        assert node.title
        assert node.category
        assert node.summary
        assert node.why_it_matters
        assert node.inputs
        assert node.calculations
        assert node.transparency_surfaces
        assert node.limitations
        assert node.sources
        for source in node.sources:
            assert source.title
            assert source.url.startswith("https://")
            assert source.note
