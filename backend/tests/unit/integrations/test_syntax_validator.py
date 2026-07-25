"""Unit tests for SyntaxValidatorDispatcher."""

from __future__ import annotations

from fetch.application.integrations.syntax_validator import SyntaxValidatorDispatcher
from fetch.domain.enums import GenerationLanguage


class TestSyntaxValidator:
    def setup_method(self) -> None:
        self.validator = SyntaxValidatorDispatcher()

    def test_valid_python_no_issues(self) -> None:
        code = "def hello():\n    return 'world'\n"
        issues = self.validator.validate(code, GenerationLanguage.PYTHON)
        assert issues == []

    def test_invalid_python_syntax_error(self) -> None:
        code = "def foo(:\n    pass\n"
        issues = self.validator.validate(code, GenerationLanguage.PYTHON)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].category == "syntax"
        assert "SyntaxError at line" in issues[0].message
        assert issues[0].field is None

    def test_typescript_unbalanced_braces_warning(self) -> None:
        code = "function hello() { return 1;"  # missing closing brace
        issues = self.validator.validate(code, GenerationLanguage.TYPESCRIPT)
        brace_warnings = [i for i in issues if "braces" in i.message]
        assert len(brace_warnings) == 1
        assert brace_warnings[0].severity == "warning"

    def test_typescript_balanced_braces_no_issues(self) -> None:
        code = "function hello() { return 1; }"
        issues = self.validator.validate(code, GenerationLanguage.TYPESCRIPT)
        brace_issues = [i for i in issues if "braces" in i.message]
        assert brace_issues == []

    def test_java_unbalanced_braces_warning(self) -> None:
        code = (
            "public class Foo { public void bar() { return; }"  # missing closing brace
        )
        issues = self.validator.validate(code, GenerationLanguage.JAVA)
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "braces" in issues[0].message

    def test_java_balanced_braces_no_issues(self) -> None:
        code = "public class Foo { public void bar() {} }"
        issues = self.validator.validate(code, GenerationLanguage.JAVA)
        assert issues == []

    def test_typescript_unbalanced_parens_warning(self) -> None:
        code = "const f = (x => x + 1;"  # unbalanced parens
        issues = self.validator.validate(code, GenerationLanguage.TYPESCRIPT)
        paren_warnings = [i for i in issues if "parentheses" in i.message]
        assert len(paren_warnings) == 1
