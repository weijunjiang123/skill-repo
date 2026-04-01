"""MetadataParser 单元测试"""

from pathlib import Path

from skill_repo.metadata import MetadataParser, SkillMetadata, SkillInfo


class TestSkillMetadataDataclass:
    def test_create(self):
        m = SkillMetadata(name="my-skill", description="A cool skill")
        assert m.name == "my-skill"
        assert m.description == "A cool skill"


class TestSkillInfoDataclass:
    def test_create(self):
        m = SkillMetadata(name="s", description="d")
        info = SkillInfo(metadata=m, category="tools", source_path=Path("/a/b"))
        assert info.metadata is m
        assert info.category == "tools"
        assert info.source_path == Path("/a/b")


class TestMetadataParserParse:
    def setup_method(self):
        self.parser = MetadataParser()

    def test_parse_valid_frontmatter(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text('---\nname: "my-skill"\ndescription: "Does things"\n---\n# Body\n', encoding="utf-8")

        result = self.parser.parse(skill_md)
        assert result.name == "my-skill"
        assert result.description == "Does things"

    def test_parse_frontmatter_without_quotes(self, tmp_path: Path):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("---\nname: test-skill\ndescription: A test skill\n---\n", encoding="utf-8")

        result = self.parser.parse(skill_md)
        assert result.name == "test-skill"
        assert result.description == "A test skill"

    def test_parse_missing_frontmatter_fallback(self, tmp_path: Path):
        skill_dir = tmp_path / "fallback-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# Just a heading\nSome content.\n", encoding="utf-8")

        result = self.parser.parse(skill_md)
        assert result.name == "fallback-skill"
        assert result.description == ""

    def test_parse_empty_file_fallback(self, tmp_path: Path):
        skill_dir = tmp_path / "empty-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("", encoding="utf-8")

        result = self.parser.parse(skill_md)
        assert result.name == "empty-skill"
        assert result.description == ""

    def test_parse_unicode_metadata(self, tmp_path: Path):
        skill_dir = tmp_path / "unicode-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text('---\nname: "中文技能"\ndescription: "这是一个中文描述"\n---\n', encoding="utf-8")

        result = self.parser.parse(skill_md)
        assert result.name == "中文技能"
        assert result.description == "这是一个中文描述"


class TestMetadataParserValidate:
    def setup_method(self):
        self.parser = MetadataParser()

    def test_validate_valid_skill(self, tmp_path: Path):
        skill_dir = tmp_path / "good-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text('---\nname: "good"\ndescription: "desc"\n---\n', encoding="utf-8")

        errors = self.parser.validate(skill_dir)
        assert errors == []

    def test_validate_missing_skill_md(self, tmp_path: Path):
        skill_dir = tmp_path / "no-md"
        skill_dir.mkdir()

        errors = self.parser.validate(skill_dir)
        assert len(errors) == 1
        assert "SKILL.md" in errors[0]

    def test_validate_empty_name(self, tmp_path: Path):
        skill_dir = tmp_path / "bad-name"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text('---\nname: ""\ndescription: "desc"\n---\n', encoding="utf-8")

        errors = self.parser.validate(skill_dir)
        assert any("name" in e for e in errors)

    def test_validate_empty_description(self, tmp_path: Path):
        skill_dir = tmp_path / "bad-desc"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text('---\nname: "ok"\ndescription: ""\n---\n', encoding="utf-8")

        errors = self.parser.validate(skill_dir)
        assert any("description" in e for e in errors)

    def test_validate_no_frontmatter_reports_empty_description(self, tmp_path: Path):
        skill_dir = tmp_path / "no-fm"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Just content\n", encoding="utf-8")

        errors = self.parser.validate(skill_dir)
        # name falls back to dir name (non-empty), but description is ""
        assert any("description" in e for e in errors)


class TestMetadataParserFormatFrontmatter:
    def setup_method(self):
        self.parser = MetadataParser()

    def test_format_basic(self):
        m = SkillMetadata(name="my-skill", description="A description")
        result = self.parser.format_frontmatter(m)
        assert result.startswith("---\n")
        assert "name:" in result
        assert "description:" in result
        assert result.strip().endswith("---")

    def test_format_then_parse_roundtrip(self, tmp_path: Path):
        original = SkillMetadata(name="roundtrip", description="test roundtrip")
        formatted = self.parser.format_frontmatter(original)

        skill_dir = tmp_path / "roundtrip"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(formatted, encoding="utf-8")

        parsed = self.parser.parse(skill_md)
        assert parsed.name == original.name
        assert parsed.description == original.description
