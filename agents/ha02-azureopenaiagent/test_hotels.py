import pytest
from main import get_available_hotels


def test_valid_request_returns_hotels():
    result = get_available_hotels("2025-08-01", "2025-08-03")
    assert "Available hotels in Seattle" in result
    assert "2025-08-01" in result
    assert "2025-08-03" in result


def test_nights_calculation():
    result = get_available_hotels("2025-08-01", "2025-08-04")
    assert "3 nights" in result


def test_total_cost_calculation():
    # Relecloud Hotel is $99/night; 2 nights = $198
    result = get_available_hotels("2025-08-01", "2025-08-03", max_price=99)
    assert "Total: $198" in result


def test_checkout_before_checkin_returns_error():
    result = get_available_hotels("2025-08-05", "2025-08-01")
    assert "Error" in result
    assert "Check-out date must be after check-in date" in result


def test_same_day_checkin_checkout_returns_error():
    result = get_available_hotels("2025-08-01", "2025-08-01")
    assert "Error" in result
    assert "Check-out date must be after check-in date" in result


def test_max_price_filters_hotels():
    result = get_available_hotels("2025-08-01", "2025-08-03", max_price=99)
    assert "Relecloud Hotel" in result
    assert "Alpine Ski House" not in result


def test_no_hotels_within_budget():
    result = get_available_hotels("2025-08-01", "2025-08-03", max_price=50)
    assert "No hotels found" in result
    assert "$50/night" in result


def test_default_max_price_returns_all_hotels():
    result = get_available_hotels("2025-08-01", "2025-08-03")
    assert "Contoso Suites" in result
    assert "Fabrikam Residences" in result
    assert "Alpine Ski House" in result
    assert "Margie's Travel Lodge" in result
    assert "Northwind Inn" in result
    assert "Relecloud Hotel" in result


def test_invalid_date_format_returns_error():
    result = get_available_hotels("01-08-2025", "03-08-2025")
    assert "Error parsing dates" in result
    assert "YYYY-MM-DD" in result


def test_invalid_date_string_returns_error():
    result = get_available_hotels("not-a-date", "also-not-a-date")
    assert "Error parsing dates" in result


def test_hotel_details_in_output():
    result = get_available_hotels("2025-08-01", "2025-08-02", max_price=200)
    assert "Location:" in result
    assert "Rating:" in result
    assert "/night" in result


def test_max_price_boundary_includes_exact_price():
    # Northwind Inn is exactly $139/night
    result = get_available_hotels("2025-08-01", "2025-08-02", max_price=139)
    assert "Northwind Inn" in result
    assert "Alpine Ski House" not in result


def test_one_night_stay():
    result = get_available_hotels("2025-08-01", "2025-08-02", max_price=99)
    assert "1 nights" in result
    assert "Total: $99" in result