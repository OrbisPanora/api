"""Resource endpoints and the resource service, on a small resources folder."""

import json

import pytest
from PIL import Image

from orbispanora_api.services import resource_service
from orbispanora_api.settings import get_settings
from orbispanora_api.utils.errors import InvalidBlockProperties


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def write_image(path, size=(16, 16), color=(10, 20, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "WEBP" if path.suffix == ".webp" else "PNG")


@pytest.fixture
def resources(tmp_path, monkeypatch):
    """A resources folder with stone (variants), a fence (multipart) and grass (tinted)."""
    root = tmp_path / "resources"
    write_json(root / "json/blockstates/stone.json", {"variants": {"": {"model": "minecraft:block/stone"}}})
    write_json(root / "json/blocks/stone.json", {"textures": {"all": "minecraft:block/stone"}})
    write_json(
        root / "json/blockstates/oak_stairs.json",
        {"variants": {"facing=north": {"model": "block/stairs_n"}, "facing=south": [{"model": "block/stairs_s"}, {"model": "block/stairs_s"}]}},
    )
    write_json(root / "json/blocks/stairs_n.json", {"textures": {"top": "block/planks", "side": "block/planks_side"}})
    write_json(root / "json/blocks/stairs_s.json", {"textures": {"all": "block/planks"}})
    write_json(
        root / "json/blockstates/oak_fence.json",
        {"multipart": [{"apply": {"model": "block/fence_post"}}, {"when": {"north": "true"}, "apply": {"model": "block/fence_side"}}]},
    )
    write_json(root / "json/blocks/fence_post.json", {"textures": {"texture": "block/planks"}})
    write_json(root / "json/blocks/fence_side.json", {"textures": {"texture": "block/planks"}})
    write_json(root / "json/blockstates/grass_block.json", {"variants": {"": {"model": "block/grass_block"}}})
    write_json(
        root / "json/blocks/grass_block.json",
        {"textures": {"all": "block/grass_block"}, "elements": [{"faces": {"up": {"tintindex": 0}}}]},
    )
    write_json(root / "json/colors/biome_tint_map.json", {"minecraft:grass_block": "grass", "minecraft:oak_leaves": "foliage"})
    write_json(root / "json/biome/plains.json", {"downfall": 0.4, "temperature": 0.8})
    write_image(root / "images/colors/grass.png", (256, 256), (1, 2, 3))
    write_image(root / "images/colors/foliage.png", (256, 256), (4, 5, 6))
    for name in ("stone", "planks", "planks_side", "fence_post", "grass_block", "fence_side"):
        for face in ("top", "left"):
            write_image(root / f"images/{name}_{face}.webp")
    monkeypatch.setenv("ORBISPANORA_RESOURCES_DIR", str(root))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


class TestImages:

    def test_existing_image(self, resources, client):
        response = client.get("/api/resources/images/stone_top.webp")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"

    def test_missing_image(self, resources, client):
        assert client.get("/api/resources/images/absent.webp").status_code == 404


class TestJsonEndpoint:

    def test_variant_block(self, resources, client):
        data = client.get("/api/resources/json", params={"id": "stone"}).json()["data"]
        assert data["type"] == "variant"
        assert set(data["resources"]) == {"top", "left"}

    def test_variant_selected_by_properties(self, resources, client):
        for facing in ("north", "south"):
            response = client.get("/api/resources/json", params={"id": "oak_stairs", "properties": json.dumps({"facing": facing})})
            assert response.status_code == 200, response.text

    def test_multipart_block(self, resources, client):
        response = client.get("/api/resources/json", params={"id": "oak_fence", "properties": json.dumps({"north": "true"})})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["type"] == "multipart"

    def test_multipart_block_needs_properties(self, resources, client):
        assert client.get("/api/resources/json", params={"id": "oak_fence"}).status_code in (400, 500)

    def test_tinted_block_takes_its_color_from_the_biome(self, resources, client):
        response = client.get("/api/resources/json", params={"id": "grass_block", "biome": "plains"})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["resources"]["color"] == "#010203"

    def test_unknown_block(self, resources, client):
        assert client.get("/api/resources/json", params={"id": "bedrock_with_a_typo"}).status_code == 404


class TestPalette:

    def test_known_and_unknown_blocks(self, resources, client):
        body = {
            "blocks": [
                {
                    "stone": [{"biome": "plains", "properties": {}, "side": 0}],
                    "unknown_block": [{"biome": "plains", "properties": {}, "side": 0}],
                }
            ]
        }
        data = client.post("/api/resources/palette", json=body).json()["data"]
        assert data["stone"][0]["type"] == "variant"
        assert data["unknown_block"] == []


class TestService:

    def test_missing_blockstate(self, resources):
        with pytest.raises(FileNotFoundError):
            resource_service.get_json_block("absent")

    def test_variants_without_properties_pick_the_first_model(self):
        assert resource_service.get_variants_block_data({"variants": {"a=b": {"model": "block/x"}}}, {}) == "block/x"

    def test_variants_with_properties_that_match_nothing_pick_the_first_model(self):
        data = {"variants": {"facing=north": {"model": "block/n"}}}
        assert resource_service.get_variants_block_data(data, {"facing": "up"}) == "block/n"

    def test_variants_with_a_list_of_models(self):
        data = {"variants": {"": [{"model": "block/a"}, {"model": "block/b"}]}}
        assert resource_service.get_variants_block_data(data, {}) in ("block/a", "block/b")

    def test_variants_that_are_malformed(self):
        with pytest.raises(InvalidBlockProperties):
            resource_service.get_variants_block_data({"variants": {}}, {})

    @pytest.mark.parametrize(
        "textures, top, left",
        [
            ({"cross": "block/rose"}, None, "rose_left.webp"),
            ({"rail": "block/rail"}, "rail_top.webp", None),
            ({"pane": "block/glass"}, None, "glass_left.webp"),
            ({"bars": "block/bars"}, None, "bars_left.webp"),
            ({"end": "block/log_end", "side": "block/log"}, "log_end_top.webp", "log_left.webp"),
            ({"top": "block/t"}, "t_top.webp", "t_left.webp"),
            ({"round": "block/stone_wheel", "pattern": "block/p"}, "stone_wheel_top.webp", "p_left.webp"),
            ({"unnamed": "block/u"}, "u_top.webp", "u_left.webp"),
        ],
    )
    def test_isometric_texture_selection(self, monkeypatch, textures, top, left):
        monkeypatch.setattr(resource_service, "get_images", lambda names: names)
        result = resource_service._get_texture_isometric({"textures": textures})
        assert result == {"top": top, "left": left}

    def test_tint_of_an_untinted_block_is_none(self, resources):
        assert resource_service.get_colors("stone", "minecraft", "plains") is None

    def test_foliage_color_uses_the_foliage_map(self, resources):
        assert resource_service.get_colors("oak_leaves", "minecraft", "plains") == "#040506"

    def test_tintindex_is_found_in_the_parent_model(self, resources):
        write_json(resources / "json/blocks/parent.json", {"elements": [{"faces": {"up": {"tintindex": 0}}}]})
        assert resource_service.check_tintindex({"parent": "block/parent"})
        assert not resource_service.check_tintindex({"textures": {}})
