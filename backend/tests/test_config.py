"""Tests for configuration parsing and validation."""

from __future__ import annotations

import json

import pytest

from app.core.config import Settings


def test_cors_origins_split_and_trimmed() -> None:
    settings = Settings(cors_origins=" http://a.test , http://b.test ,, ")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_ndvi_thresholds_parsed() -> None:
    settings = Settings(ndvi_class_thresholds="0.15,0.35,0.55,0.75")
    assert settings.ndvi_class_threshold_list == [0.15, 0.35, 0.55, 0.75]


def test_ndvi_thresholds_reject_wrong_count() -> None:
    settings = Settings(ndvi_class_thresholds="0.2,0.4,0.6")
    with pytest.raises(ValueError, match="exactly 4"):
        _ = settings.ndvi_class_threshold_list


def test_ndvi_thresholds_reject_descending() -> None:
    settings = Settings(ndvi_class_thresholds="0.8,0.6,0.4,0.2")
    with pytest.raises(ValueError, match="ascending"):
        _ = settings.ndvi_class_threshold_list


def test_ndvi_thresholds_reject_non_numeric() -> None:
    settings = Settings(ndvi_class_thresholds="0.2,0.4,high,0.8")
    with pytest.raises(ValueError, match="numeric"):
        _ = settings.ndvi_class_threshold_list


def test_log_level_normalised_to_upper() -> None:
    assert Settings(log_level="debug").log_level == "DEBUG"


def test_log_level_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="log_level"):
        Settings(log_level="chatty")


def test_service_account_key_json_parsed() -> None:
    payload = {"type": "service_account", "client_email": "svc@example.iam.gserviceaccount.com"}
    settings = Settings(ee_service_account_key_json=json.dumps(payload))
    assert settings.service_account_key_dict == payload
    assert settings.has_service_account_credentials is True


def test_service_account_key_json_rejects_malformed() -> None:
    settings = Settings(ee_service_account_key_json="{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        _ = settings.service_account_key_dict


def test_no_service_account_credentials_by_default() -> None:
    settings = Settings(ee_service_account_key_file=None, ee_service_account_key_json=None)
    assert settings.has_service_account_credentials is False
    assert settings.service_account_key_dict is None


def test_key_file_alone_counts_as_service_account() -> None:
    settings = Settings(ee_service_account_key_file="./secrets/key.json")
    assert settings.has_service_account_credentials is True
