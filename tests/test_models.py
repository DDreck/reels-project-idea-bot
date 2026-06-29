from inspiration_pipeline.models import Classification


def test_classification_from_json():
    data = {
        "category": "3d-print",
        "title": "Print-in-place hinge",
        "summary": "A clever hinge.",
        "key_points": ["no supports", "PLA"],
        "domain": "Projects",
        "is_new_category": False,
        "category_description": "",
    }
    cls = Classification.from_json(data)
    assert cls.category == "3d-print"
    assert cls.domain == "Projects"
    assert cls.key_points == ["no supports", "PLA"]


def test_classification_from_json_defaults_missing_optional():
    cls = Classification.from_json(
        {"category": "workout", "title": "T", "summary": "S",
         "key_points": [], "domain": "Health"}
    )
    assert cls.is_new_category is False
    assert cls.category_description == ""
