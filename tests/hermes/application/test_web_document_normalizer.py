import pytest
from hermes.application.web_document_normalizer import WebDocumentNormalizer


def test_normalizer_extracts_title_and_metadata():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Product Spec - High Quality Desk Lamp</title>
        <meta name="description" content="Detailed specs of the desk lamp">
        <meta name="author" content="John Doe">
        <meta property="og:site_name" content="ReviewSite">
        <link rel="canonical" href="https://example.com/lamp-canonical">
    </head>
    <body>
        <main>
            <h1>Desk Lamp Specifications</h1>
            <p>This lamp features 3 color modes and touch controls with a sleek modern design.</p>
            <p>Built with high quality aluminum alloy and energy-efficient LED panels that reduce eye strain during long reading sessions.</p>
            <p>Includes a built-in USB charging port and a 45-minute auto-off timer for bedtime reading convenience.</p>
        </main>
    </body>
    </html>
    """
    normalizer = WebDocumentNormalizer()
    res = normalizer.normalize(html, base_url="https://example.com/lamp")
    assert res.title == "Product Spec - High Quality Desk Lamp"
    assert res.metadata["description"] == "Detailed specs of the desk lamp"
    assert res.metadata["author"] == "John Doe"
    assert res.metadata["site_name"] == "ReviewSite"
    assert res.metadata["canonical_url"] == "https://example.com/lamp-canonical"
    assert "Desk Lamp Specifications" in res.markdown
    assert "3 color modes" in res.markdown
    assert not res.dynamic_fallback_recommended


def test_normalizer_detects_dynamic_shell():
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>App Shell</title></head>
    <body>
        <div id="root">Loading...</div>
        <script src="bundle.js"></script>
        <script src="app.js"></script>
    </body>
    </html>
    """
    normalizer = WebDocumentNormalizer()
    res = normalizer.normalize(html, base_url="https://example.com/app")
    assert res.dynamic_fallback_recommended is True


def test_normalizer_removes_unwanted_tags():
    html = """
    <html>
    <body>
        <nav><a href="/">Home</a></nav>
        <main>
            <p>Main content here with enough descriptive text to simulate a full section of static content.</p>
            <p>Second paragraph providing additional context and verification for normalization without triggering dynamic fallback.</p>
            <p>Third paragraph adding detailed specifications and information about the product under review.</p>
        </main>
        <footer>Copyright 2026</footer>
        <script>console.log('secret');</script>
        <style>body { color: red; }</style>
    </body>
    </html>
    """
    normalizer = WebDocumentNormalizer()
    res = normalizer.normalize(html, base_url="https://example.com")
    assert "Main content here" in res.markdown
    assert "Home" not in res.markdown
    assert "Copyright 2026" not in res.markdown
    assert "console.log" not in res.markdown
    assert "color: red" not in res.markdown
