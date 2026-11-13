# Inline data.json into the concepts page: python3 data/build.py (run from docs/design)
import pathlib
here=pathlib.Path(__file__).parent
t=(here.parent/"concepts.template.html").read_text()
(here.parent/"concepts.html").write_text(t.replace("__DATA__",(here/"data.json").read_text()))
