import json
import os
from utils.errors import InvalidBlockProperties
from models.responses import BlockJsonDataResponse

def get_json_block(id: str, namespace: str = "minecraft", properties: str = "{}") -> BlockJsonDataResponse:

    blockstate_data = _get_blockstate_data(id)
    model_data = _get_block_data(blockstate_data, json.loads(properties))

    texture = _get_texture_isometric(model_data)

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
            model = block_data["variants"][""]["model"]
        except:
            raise InvalidBlockProperties("Properties are defined but must be empty")
            
    model_name = model.split("/")[-1]
    json_file = model_name + '.json'

    filepath = os.path.join(blocks_path, json_file)

    with open(filepath, 'r') as f:
            model_data = json.load(f)
    return model_data

def _get_texture_isometric(model_data: dict):
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

    return texture
