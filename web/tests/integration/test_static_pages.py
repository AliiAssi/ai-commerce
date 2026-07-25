from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set"
)

# every destination the header and footer link a guest to
STOREFRONT_LINKS = [
    "/",
    "/catalog",
    "/makers",
    "/about",
    "/shipping",
    "/cart",
    "/login",
    "/register",
]


# follow redirects: /cart sends guests through /login, which must itself land on 200
async def test_header_and_footer_links_resolve(client, _clean):
    for path in STOREFRONT_LINKS:
        response = await client.get(path, follow_redirects=True)
        assert response.status_code == 200, f"{path} -> {response.status_code}"


async def test_static_pages_carry_their_copy(client, _clean):
    makers = await client.get("/makers")
    assert "Koura" in makers.text and "Tripoli" in makers.text

    about = await client.get("/about")
    assert "demonstration" in about.text

    shipping = await client.get("/shipping")
    assert "cancelled" in shipping.text


async def test_shelves_partial_lists_categories(client, catalog):
    response = await client.get("/partials/shelves")
    assert response.status_code == 200
    assert "Gear" in response.text
    assert "/catalog?category=gear" in response.text
    # the always-present summary row
    assert "Everything" in response.text


async def test_nav_marks_the_active_page(client, _clean):
    response = await client.get("/makers")
    assert 'aria-current="page"' in response.text
    # the home page highlights nothing
    home = await client.get("/")
    assert 'aria-current="page"' not in home.text
