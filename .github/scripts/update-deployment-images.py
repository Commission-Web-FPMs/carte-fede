"""Update the image blocks owned by the publication workflow, preserving other values."""

import os
from pathlib import Path
import re

path = Path("values.yaml")
content = path.read_text()
tag = os.environ["GITHUB_SHA"]
repository = os.environ["IMAGE_REPOSITORY"]
branch = os.environ.get("GITHUB_REF_NAME", "main")
expected = "ghcr.io/commission-web-fpms/carte-fede" + ("-dev" if branch == "develop" else "")
if branch not in {"main", "develop"} or repository != expected or not re.fullmatch(r"[0-9a-f]{40}", tag):
    raise RuntimeError("Publication branch/image/SHA isolation failed")
if branch == "develop" and "carte_fede_dev" not in content:
    raise RuntimeError("Target chart is not explicitly DEV")


def replace_field(pattern, value):
    global content
    content, count = re.subn(pattern, lambda match: match[1] + value, content, count=1)
    if count != 1:
        raise RuntimeError("Image field missing in deployment values.yaml")


replace_field(r"(?m)(^image:\n(?:[ \t]+[^\n]*\n)*?  repository: *)[^\n]*", repository)
replace_field(r"(?m)(^image:\n(?:[ \t]+[^\n]*\n)*?  tag: *)[^\n]*", tag)

# Support the old chart until the frontend templates are merged.
if not re.search(r"(?m)^frontend:", content):
    content += (
        "\nfrontend:\n  image:\n"
        f"    repository: {repository}-frontend\n"
        "    pullPolicy: IfNotPresent\n"
        f"    tag: {tag}\n"
    )
else:
    replace_field(r"(?m)(^frontend:\n(?:[ \t]+[^\n]*\n)*?    repository: *)[^\n]*",
                  repository + "-frontend")
    replace_field(r"(?m)(^frontend:\n(?:[ \t]+[^\n]*\n)*?    tag: *)[^\n]*", tag)

path.write_text(content)
