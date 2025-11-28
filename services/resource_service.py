import json
import os
from utils.errors import InvalidBlockProperties
from models.responses import BlockJsonDataResponse
import logging

LOGGER = logging.getLogger(__file__)

def get_json_block(id: str, namespace: str = "minecraft", properties: str = "{}", biome: str = "biome") -> BlockJsonDataResponse:

    blockstate_data = _get_blockstate_data(id)
    model_data = _get_block_data(blockstate_data, json.loads(properties))

    texture = _get_texture_isometric(model_data, biome)

    json_data = {
        "block_name": id,
        "textures": texture
    }     
    return BlockJsonDataResponse(**json_data)

def _get_blockstate_data(name: str) -> dict:
    blockstates_path = f"resources/json/blockstates"
    filename = name + '.json'

    block = os.path.join(blockstates_path, filename)

    if not os.path.exists(block):
        raise FileNotFoundError("json file: {block} not found")
        
    with open(block, 'r') as f:
        blockstate_data = json.load(f)
    return blockstate_data

def _get_block_data(blockstate_data: dict, properties: dict) -> dict:
    blocks_path = f"resources/json/blocks"

    if properties != {}:
        try:
            for state, props in blockstate_data["variants"].items():
                attributes = dict(part.split("=") for part in state.split(","))

                if all(k in properties and properties[k] == v for k, v in attributes.items()):
                    model = props["model"]
                    break
        except:
            raise InvalidBlockProperties("Properties are undefined but must be defined")
    else:
        try:
            model = blockstate_data["variants"][""]["model"]
        except:
            raise InvalidBlockProperties("Properties are defined but must be empty")
            
    model_name = model.split("/")[-1]
    json_file = model_name + '.json'

    filepath = os.path.join(blocks_path, json_file)

    with open(filepath, 'r') as f:
        model_data = json.load(f)
    return model_data

def check_parent_tintindex(model_data: dict) -> bool:
    blocks_path = f"resources/json/blocks"
    parent_name = model_data["parent"].split("/")[-1] +'.json'
    filepath = os.path.join(blocks_path, parent_name)

    with open(filepath, 'r') as f:
        parent_data= json.load(f)

    LOGGER.debug(parent_data)
    if "elements" in parent_data:
        if ("tintindex" in parent_data["elements"][0]["faces"]["down"]):
            return True
    return False

def get_biomes_values(biome: str) -> tuple[float,float]:
    biome_path = f"resources/json/biome"
    biome = biome.replace(" ", "_").lower() + '.json'

    file = os.path.join(biome_path, biome)

    with open(file, 'r') as f:
        biome_data = json.load(f)

    downfall = biome_data["downfall"]
    temperature = biome_data["temperature"]
    
    return (downfall, temperature)

def _get_texture_isometric(model_data: dict, biome: str):
    texture = {}
    texture_top_iso = None
    texture_left_iso = None

    if "top" in model_data["textures"]:
        texture_top_iso = model_data["textures"]["top"]
    elif "end" in model_data["textures"]:
        texture_top_iso = model_data["textures"]["end"]
    elif "all" in model_data["textures"]:
        texture_top_iso = model_data["textures"]["all"]
    elif "texture" in model_data["textures"]:
        texture_top_iso = model_data["textures"]["texture"]
    elif "round" in model_data["textures"]:  
        texture_top_iso = model_data["textures"]["round"]
    elif model_data["textures"]:
        first_key = next(iter(model_data["textures"]))
        texture_top_iso = model_data["textures"][first_key]


        
    if "side" in model_data["textures"]:
        texture_left_iso = model_data["textures"]["side"]
    elif "all" in model_data["textures"]:
        texture_left_iso = model_data["textures"]["all"]
    elif "texture" in model_data["textures"]:
        texture_left_iso = model_data["textures"]["texture"]
    elif "bars" in model_data["textures"]: 
        texture_left_iso = model_data["textures"]["bars"]
    else:
        texture_left_iso = texture_top_iso


    if texture_top_iso:
        texture_top_name = texture_top_iso.split("/")[-1]
        texture["top"] = f"{texture_top_name}_top.webp"
    else:
        texture["top"] = "default_top.webp"

    if texture_left_iso:
        texture_left_name = texture_left_iso.split("/")[-1]
        texture["left"] = f"{texture_left_name}_left.webp"
    else:
        texture["left"] = "default_left.webp"

    if check_parent_tintindex(model_data):
        if biome == "biome":
            raise Exception()
        color_data = get_biomes_values(biome)
        texture["downfall"] = color_data[0]
        texture["temperature"] = color_data[1]

    return texture
