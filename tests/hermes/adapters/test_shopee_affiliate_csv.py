from __future__ import annotations

import pytest

from hermes.adapters.affiliate.shopee_csv import ShopeeAffiliateCsvSource


def test_csv_adapter_normalizes_vietnamese_money_and_aliases(tmp_path):
    path = tmp_path / "feed.csv"
    path.write_text(
        "item_id,product_name,category,price,sold,rating,commission,product_link,image\n"
        "101,RGB Mouse,mouse,\"349.000 Ä‘\",\"12,3k\",4.8,12%,https://shopee.vn/a,https://img/a.jpg\n",
        encoding="utf-8",
    )

    rows = ShopeeAffiliateCsvSource(path).load("42")

    assert rows[0].external_product_id == "101"
    assert rows[0].price_vnd == 349_000
    assert rows[0].sold_count == 12_300
    assert rows[0].commission_rate == 0.12
    assert rows[0].authorization_scope == "user_export"
    assert rows[0].content_hash


def test_csv_adapter_rejects_ambiguous_price_and_keeps_content_hash_deterministic(tmp_path):
    path = tmp_path / "feed.csv"
    path.write_text(
        "item_id,product_name,category,price,product_link\n"
        "101,RGB Mouse,mouse,349000,https://shopee.vn/a\n"
        "102,RGB Mouse,mouse,\"349.000 Ä‘ (giảm 10%)\",https://shopee.vn/b\n",
        encoding="utf-8",
    )
    source = ShopeeAffiliateCsvSource(path)

    first = source.load_batch("42")
    second = source.load_batch("42")

    assert len(first.candidates) == 1
    assert first.candidates[0].content_hash == second.candidates[0].content_hash
    assert first.errors[0].row_number == 3
    assert "price" in first.errors[0].message


def test_invalid_rows_are_reported_without_dropping_valid_rows(tmp_path):
    path = tmp_path / "feed.csv"
    path.write_text(
        "item_id,product_name,category,price,product_link\n"
        "101,RGB Mouse,mouse,349000,https://shopee.vn/a\n"
        "102,,mouse,349000,https://shopee.vn/b\n",
        encoding="utf-8",
    )

    batch = ShopeeAffiliateCsvSource(path).load_batch("42")

    assert len(batch.candidates) == 1
    assert batch.errors[0].row_number == 3
    assert "name" in batch.errors[0].message


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sold", "12 units", "integer"),
        ("reviews", "-1", "integer"),
        ("rating", "5.1", "rating"),
        ("commission", "-2%", "commission"),
    ],
)
def test_csv_source_strictly_validates_numeric_domains(tmp_path, field, value, message):
    path = tmp_path / "products.csv"
    row = {
        "item_id": "101",
        "product_name": "Mouse",
        "category": "mouse",
        "price": "300000",
        "sold": "12",
        "rating": "4.8",
        "reviews": "3",
        "commission": "10%",
        "product_link": "https://example.test/101",
    }
    row[field] = value
    path.write_text(
        ",".join(row) + "\n" + ",".join(str(row[key]) for key in row) + "\n",
        encoding="utf-8",
    )

    batch = ShopeeAffiliateCsvSource(path).load_batch("42")

    assert batch.candidates == []
    assert message in batch.errors[0].message
