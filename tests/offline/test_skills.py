import re
from pathlib import Path

from nxkit.registry import Registry

SKILLS = Path(__file__).resolve().parents[2] / "skills"
NAMES = ("nx-modify", "nx-mold-template", "nx-plugin-verify")
HEADINGS = ("## 何时用", "## 步骤", "## 硬规则")


def test_skill_files_exist():
    for name in NAMES:
        assert (SKILLS / name / "SKILL.md").is_file(), name


def test_skill_sections():
    for path in sorted(SKILLS.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        for heading in HEADINGS:
            assert heading in text, (path, heading)


def test_referenced_files_exist():
    pattern = re.compile(r"\((references/[^)]+|templates/[^)]+)\)")
    for path in sorted(SKILLS.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        for ref in pattern.findall(text):
            assert (path.parent / ref).is_file(), (path, ref)


def test_tool_names_exist(contract_dir):
    registry = Registry(contract_dir)
    for path in sorted(SKILLS.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        for name in sorted(set(re.findall(r"\bnx_[a-z_]+\b", text))):
            assert name in registry.tools, (path, name)
