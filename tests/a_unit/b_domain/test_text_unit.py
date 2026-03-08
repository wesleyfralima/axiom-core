import pytest

from a_core.exceptions import ValidationException
from b_domain.value_objects import Title, Description


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def valid_title() -> Title:
    """Provide a valid Title instance."""
    return Title("Valid Title")


@pytest.fixture
def valid_description() -> Description:
    """Provide a valid Description instance."""
    return Description("This is a valid description.")


# ============================================================
# Group 1: Title Creation and Validation
# ============================================================

@pytest.mark.unit
def test_title_create_with_valid_value(valid_title: Title) -> None:
    """Ensure Title is created successfully with a valid value."""

    assert isinstance(valid_title, Title)
    assert valid_title.value == "Valid Title"


@pytest.mark.unit
def test_title_cannot_be_empty() -> None:
    """Ensure empty title raises ValidationException."""

    with pytest.raises(ValidationException):
        Title(None)

    with pytest.raises(ValidationException):
        Title()

    with pytest.raises(ValidationException):
        Title("")


@pytest.mark.unit
def test_title_cannot_exceed_max_length() -> None:
    """Ensure title longer than 255 characters raises ValidationException."""

    long_title: str = "a" * 256
    with pytest.raises(ValidationException):
        Title(long_title)


@pytest.mark.unit
def test_title_must_have_at_least_three_non_whitespace_chars() -> None:
    """Ensure title with fewer than 3 valid characters raises ValidationException."""

    with pytest.raises(ValidationException):
        Title("a    ")

    with pytest.raises(ValidationException):
        Title("    a")

    with pytest.raises(ValidationException):
        Title("  a  ")

    with pytest.raises(ValidationException):
        Title(" a ")


# ============================================================
# Group 2: Title Equality and String Behavior
# ============================================================

@pytest.mark.unit
def test_title_equality_with_same_title_object(valid_title: Title) -> None:
    """Ensure Title objects with same value are equal."""

    other: Title = Title("Valid Title")
    assert valid_title == other


@pytest.mark.unit
def test_title_equality_with_string(valid_title: Title) -> None:
    """Ensure Title can be compared directly with a string."""

    assert valid_title == "Valid Title"


@pytest.mark.unit
def test_title_inequality_with_different_value(valid_title: Title) -> None:
    """Ensure Title is not equal to different string values."""

    assert valid_title != "Another Title"


@pytest.mark.unit
def test_title_string_representation(valid_title: Title) -> None:
    """Ensure __str__ returns the raw title value."""

    assert str(valid_title) == "Valid Title"


# ============================================================
# Group 3: Description Creation and Validation
# ============================================================

@pytest.mark.unit
def test_description_create_with_valid_value(valid_description: Description) -> None:
    """Ensure Description is created successfully with valid content."""

    assert isinstance(valid_description, Description)
    assert valid_description.value == "This is a valid description."


@pytest.mark.unit
def test_description_empty_param() -> None:
    """Ensure Description is accepted based on empty params (no param, None, and empty str)."""

    description: Description = Description(None)
    assert description.value is None

    description: Description = Description()
    assert description.value is None

    description: Description = Description("")
    assert description.value == ""


@pytest.mark.unit
def test_description_cannot_exceed_max_length() -> None:
    """Ensure description longer than 5000 characters raises ValidationException."""

    long_description: str = "a" * 5001
    with pytest.raises(ValidationException):
        Description(long_description)


# ============================================================
# Group 4: Description Equality and String Behavior
# ============================================================

@pytest.mark.unit
def test_description_equality_with_same_description_object(valid_description: Description) -> None:
    """Ensure Description objects with same value are equal."""

    other: Description = Description("This is a valid description.")
    assert valid_description == other


@pytest.mark.unit
def test_description_equality_with_string(valid_description: Description) -> None:
    """Ensure Description can be compared directly with a string."""

    assert valid_description == "This is a valid description."


@pytest.mark.unit
def test_description_inequality_with_different_value(valid_description: Description) -> None:
    """Ensure Description is not equal to different string values."""

    assert valid_description != "Another description"


@pytest.mark.unit
def test_description_string_representation(valid_description: Description) -> None:
    """Ensure __str__ returns the raw description value."""

    assert str(valid_description) == "This is a valid description."
