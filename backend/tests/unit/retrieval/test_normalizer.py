"""Unit tests for QueryNormalizer.

No external services required. Pure Python only.
"""

import pytest

from fetch.application.retrieval.normalizer import NormalizedQuery, QueryNormalizer


@pytest.fixture
def normalizer() -> QueryNormalizer:
    return QueryNormalizer()


# ---------------------------------------------------------------------------
# HTTP method extraction
# ---------------------------------------------------------------------------


def test_extracts_http_method_post(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("How do I POST to /v1/customers?")
    assert result.method == "POST"


def test_extracts_http_method_get(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("What does GET /v1/payments/{id} return?")
    assert result.method == "GET"


def test_extracts_http_method_delete(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("Can I DELETE a subscription via the API?")
    assert result.method == "DELETE"


def test_extracts_http_method_put(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("How do I PUT an update to a customer record?")
    assert result.method == "PUT"


def test_extracts_http_method_patch(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("Use PATCH to partially update a resource.")
    assert result.method == "PATCH"


def test_no_method_when_absent(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("What fields does PaymentIntent have?")
    assert result.method is None


def test_method_case_insensitive_lower(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("how do I post to /v1/customers?")
    assert result.method == "POST"


# ---------------------------------------------------------------------------
# Path pattern extraction
# ---------------------------------------------------------------------------


def test_extracts_path_with_param(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("What does GET /v1/payments/{id} return?")
    assert result.path_pattern == "/v1/payments/{id}"


def test_extracts_plain_path(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("How do I POST to /v1/customers?")
    assert result.path_pattern == "/v1/customers"


def test_extracts_nested_path(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("Tell me about /v2/users/{user_id}/addresses/{addr_id}")
    assert result.path_pattern == "/v2/users/{user_id}/addresses/{addr_id}"


def test_no_path_when_absent(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("How does createCustomer work?")
    assert result.path_pattern is None


# ---------------------------------------------------------------------------
# Operation ID extraction
# ---------------------------------------------------------------------------


def test_extracts_camel_case_operation_id(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("How does createCustomer work?")
    assert result.operation_id == "createCustomer"


def test_extracts_snake_case_operation_id(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("What does create_customer do?")
    assert result.operation_id == "create_customer"


def test_extracts_list_verb_snake_case(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("How does list_payments behave?")
    assert result.operation_id == "list_payments"


def test_no_operation_id_when_absent(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("What does GET /v1/payments/{id} return?")
    assert result.operation_id is None


# ---------------------------------------------------------------------------
# Schema name extraction
# ---------------------------------------------------------------------------


def test_extracts_pascal_case_schema(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("What fields does PaymentIntent have?")
    assert "PaymentIntent" in result.schema_names


def test_extracts_simple_compound_schema(normalizer: QueryNormalizer) -> None:
    # "Customer" has no internal capital, but CustomerAddress would qualify
    result2 = normalizer.normalize("Can you describe the CustomerAddress object?")
    assert "CustomerAddress" in result2.schema_names


def test_common_pascal_words_excluded(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("How does the API handle errors?")
    # "How", "Api" are in the exclusion list
    assert "How" not in result.schema_names
    assert "Api" not in result.schema_names


def test_multiple_schema_names(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("What is the relationship between PaymentIntent and PaymentMethod?")
    assert "PaymentIntent" in result.schema_names
    assert "PaymentMethod" in result.schema_names


# ---------------------------------------------------------------------------
# Status code extraction
# ---------------------------------------------------------------------------


def test_extracts_401_status_code(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("When does the API return 401?")
    assert "401" in result.status_codes


def test_extracts_404_status_code(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("What happens when I get a 404 error?")
    assert "404" in result.status_codes


def test_extracts_multiple_status_codes(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("Does the endpoint return 200 or 201 on success?")
    assert "200" in result.status_codes
    assert "201" in result.status_codes


def test_no_status_code_when_absent(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("How does pagination work?")
    assert result.status_codes == []


def test_out_of_range_number_not_extracted(normalizer: QueryNormalizer) -> None:
    # 700 is outside 100-599
    result = normalizer.normalize("The limit is 700 per page.")
    assert "700" not in result.status_codes


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------


def test_keywords_exclude_stop_words(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("How do I authenticate with the API?")
    lower_keywords = [k.lower() for k in result.keywords]
    assert "how" not in lower_keywords
    assert "do" not in lower_keywords
    assert "the" not in lower_keywords


def test_keywords_exclude_already_extracted(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("How do I POST to /v1/customers?")
    lower_keywords = [k.lower() for k in result.keywords]
    assert "post" not in lower_keywords
    # path is stripped before tokenisation
    assert "v1" not in lower_keywords


def test_keywords_contain_significant_terms(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("How do I authenticate with the API?")
    lower_keywords = [k.lower() for k in result.keywords]
    assert "authenticate" in lower_keywords


# ---------------------------------------------------------------------------
# Complex multi-identifier query
# ---------------------------------------------------------------------------


def test_complex_query_all_fields(normalizer: QueryNormalizer) -> None:
    question = "When does POST /v1/payments return 422 for an invalid PaymentIntent?"
    result = normalizer.normalize(question)

    assert result.raw_text == question
    assert result.method == "POST"
    assert result.path_pattern == "/v1/payments"
    assert "422" in result.status_codes
    assert "PaymentIntent" in result.schema_names


def test_normalized_query_is_frozen(normalizer: QueryNormalizer) -> None:
    result = normalizer.normalize("How does createCustomer work?")
    assert isinstance(result, NormalizedQuery)
    with pytest.raises((AttributeError, TypeError)):
        result.method = "DELETE"  # type: ignore[misc]
