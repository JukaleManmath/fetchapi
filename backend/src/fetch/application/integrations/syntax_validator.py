from __future__ import annotations

from fetch.domain.entities import ValidationIssue
from fetch.domain.enums import GenerationLanguage


class SyntaxValidatorDispatcher:
    def validate(
        self, code: str, language: GenerationLanguage
    ) -> list[ValidationIssue]:
        if language == GenerationLanguage.PYTHON:
            return self._validate_python(code)
        elif language == GenerationLanguage.TYPESCRIPT:
            return self._validate_typescript(code)
        elif language == GenerationLanguage.JAVA:
            return self._validate_java(code)
        return []

    def _validate_python(self, code: str) -> list[ValidationIssue]:
        import ast

        try:
            ast.parse(code)
            return []
        except SyntaxError as e:
            return [
                ValidationIssue(
                    severity="error",
                    category="syntax",
                    message=f"SyntaxError at line {e.lineno}: {e.msg}",
                    field=None,
                )
            ]

    def _validate_typescript(self, code: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if code.count("{") != code.count("}"):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="syntax",
                    message="Unbalanced braces in TypeScript code",
                    field=None,
                )
            )
        if code.count("(") != code.count(")"):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="syntax",
                    message="Unbalanced parentheses in TypeScript code",
                    field=None,
                )
            )
        return issues

    def _validate_java(self, code: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if code.count("{") != code.count("}"):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="syntax",
                    message="Unbalanced braces in Java code",
                    field=None,
                )
            )
        return issues
