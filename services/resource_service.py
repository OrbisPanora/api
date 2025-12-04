import json
import os
from utils.errors import InvalidBlockProperties
from models.responses import BlockJsonDataResponse
import logging
import random
from PIL import Image
import base64
from io import BytesIO
from typing import List, Dict, Union, Optional

LOGGER = logging.getLogger(__file__)

def get_json_block(id: str, namespace: str = "minecraft", properties: str = "{}", biome: str = "biome") -> BlockJsonDataResponse:

    blockstate_data = _get_blockstate_data(id)
    if isinstance(properties, dict):
        model_data = _get_block_data(id=id, namespace=namespace, blockstate_data=blockstate_data, properties=properties, biome=biome)
    else:
        model_data = _get_block_data(id=id, namespace=namespace, blockstate_data=blockstate_data, properties=json.loads(properties), biome=biome)
    return BlockJsonDataResponse(**model_data)

def _get_blockstate_data(name: str) -> dict:
    blockstates_path = f"resources/json/blockstates"
    filename = name + '.json'

    block = os.path.join(blockstates_path, filename)

    if not os.path.exists(block):
        raise FileNotFoundError("json file: {block} not found")
        
    with open(block, 'r') as f:
        blockstate_data = json.load(f)
    return blockstate_data

def get_variants_block_data(blockstate_data: dict, properties: dict):
    if properties != {}:
        try:
            model = None
            for state, props in blockstate_data["variants"].items():
                if state != "":
                    attributes = dict(part.split("=") for part in state.split(","))
                    if all(k in properties and properties[k] == v for k, v in attributes.items()):
                        if isinstance(blockstate_data['variants'][state], list):
                            lenght_variants = len(blockstate_data["variants"][state])
                            nb = random.randint(0,lenght_variants-1)
                            model = blockstate_data["variants"][state][nb]["model"]
                        else:
                            model = props["model"]
                        break
            if model == None:
                firstKey = next(iter(blockstate_data['variants']))
                model = blockstate_data["variants"][firstKey]["model"]
        except:
            raise InvalidBlockProperties("Properties are undefined but must be defined")
    else:
        try:
            firstKey = next(iter(blockstate_data['variants']))
            if isinstance(blockstate_data['variants'][firstKey], list):
                lenght_variants = len(blockstate_data["variants"][firstKey])
                nb = random.randint(0,lenght_variants-1)
                nb = random.randint(0,lenght_variants-1)
                model = blockstate_data["variants"][firstKey][nb]["model"]
            else:
                model = blockstate_data["variants"][firstKey]["model"]
                model = blockstate_data["variants"][firstKey]["model"]
        except:
            raise InvalidBlockProperties("Properties are defined but must be empty")
    return model

def get_multiparts_block_data(blockstate_data: dict, properties: dict):
    if properties == {}:
        raise InvalidBlockProperties("Properties are undefined but must be defined")
    try :
        cores : List[str] = []
        connexions: List[str] = []
        overlays: List[str] = []

        data = blockstate_data['multipart']
        print("===================start================")
        #print(data)
        for part in data:
            apply = part['apply']['model'].split("/")[-1]
            if 'when' not in part:
                cores.append({'apply':apply})
            elif all(k in properties and str(properties[k]) == v for k, v in part['when'].items()):
                model = {
                    'apply': apply,
                    'when': {key: value for key, value in part['when'].items()}
                }
                print("part:", part['when'].keys(), " values:", part['when'].values())
                if all(key in ['up', 'age'] for key in part['when'].keys()):
                    cores.append(model)
                elif all(key in ['north', 'south', 'east', 'west'] for key in part['when'].keys()):
                    connexions.append(model)
                # elif all(part['when'].keys() not in ['north', 'south', 'east', 'west'] and part['when'].values in ['true', 'false']):
                #     cores.append(part)
                else:
                    overlays.append(model)
        model = {
            'cores': cores,
            'connexions': connexions,
            'overlays': overlays
        }
        print(model)
    except:
        raise Exception
    return model

def _get_block_data(blockstate_data: dict, properties: dict, id:str, namespace: str, biome: str) -> dict:
    blocks_path = f"resources/json/blocks"

    if "variants" in blockstate_data:
        model = get_variants_block_data(blockstate_data, properties)  
        model_name = model.split("/")[-1]
        json_file = model_name + '.json'

        filepath = os.path.join(blocks_path, json_file)

        with open(filepath, 'r') as f:
            model_data = json.load(f)   

        texture = _get_texture_isometric(model_data)
        if check_tintindex(model_data):
            if biome == "biome":
                raise Exception()
            color = get_colors(id, namespace, biome)
            texture["color"] = color 
        results = {
            'block_name': id,
            'resources': texture,
            'type': 'variant'
        }
    else:
        results = {'block_name': id, 'resources': {'params': []}, 'type': 'multipart'}
        models = get_multiparts_block_data(blockstate_data, properties)
        for categorie in models.keys():
            for model in models[categorie]:
                model_name = model['apply']
                json_file = model_name + '.json'

                filepath = os.path.join(blocks_path, json_file)
                
                with open(filepath, 'r') as f:
                    model_data = json.load(f)  
                texture = _get_texture_isometric(model_data)
                if check_tintindex(model_data):
                    if biome == "biome":
                        raise Exception()
                    color = get_colors(id, namespace, biome)
                    texture["color"] = color  
                texture['categorie'] = categorie
                if 'when' in model:
                    texture['when'] = model['when']
                else:
                    texture['when'] = None
                result = {
                    'block_name': model_name,
                    'textures': texture,
                } 
                results['resources']['params'].append(result)
    return results

def check_tintindex(model_data: dict) -> bool:
    if has_tintindex(model_data):
        return True

    blocks_path = f"resources/json/blocks"
    if 'parent' in model_data:
        parent_name = model_data["parent"].split("/")[-1] +'.json'
        filepath = os.path.join(blocks_path, parent_name)

        with open(filepath, 'r') as f:
            parent_data= json.load(f)
        return has_tintindex(parent_data)
    return False

def has_tintindex(data: dict) -> bool:
    if "elements" in data:
        for element in data["elements"]:
            if "faces" in element:
                for face in element["faces"]:
                    if "tintindex" in element["faces"][face]:
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

def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def get_images(textures: dict):
    images = {}
    image_path = f"resources/images/"
    for key, value in textures.items():
        if value != None:
            img_base64 = image_to_base64(image_path + value)
            images[key] = img_base64
        else:
            images[key] = None

    return images

def _get_texture_isometric(model_data: dict):
    # Get the 'textures' dictionary, defaulting to an empty dict if not present.
    textures_source = model_data.get("textures", {})
    texture = {}
    
    # Initialize isometric texture paths.
    # Set to None if the face should be masked/hidden.
    iso_top_path = None
    iso_side_path = None

    # --- STEP 1: Handle special (non-cubic) cases with masking ---
    # These blocks require either the top or the side face to be hidden.
    
    if "cross" in textures_source:
        # E.g., Flowers, Grass. Only render the sides (vertical plane).
        iso_side_path = textures_source["cross"]
        # iso_top_path remains None (masked)
    
    elif "rail" in textures_source:
        # E.g., Rail. Only render the top.
        iso_top_path = textures_source["rail"]
        # iso_side_path remains None (masked)
        
    elif "pane" in textures_source or "bars" in textures_source:
        # E.g., Glass panes, Iron bars. Only render the sides (the post/bar texture).
        if "pane" in textures_source:
            iso_side_path = textures_source["pane"]
        elif "bars" in textures_source:
            iso_side_path = textures_source["bars"]
        # iso_top_path remains None (masked)

    # --- STEP 2: Handle cubic and composite blocks (full cube rendering) ---
    # If paths are still None, it's a cube-type block (or slab, stairs, etc.).
    if iso_top_path is None and iso_side_path is None:
        
        # A. Determine the Isometric TOP face (Priority: top > end > all > texture)
        if "top" in textures_source:
            iso_top_path = textures_source["top"]
        elif "end" in textures_source:  # Log/Pillar type
            iso_top_path = textures_source["end"]
        elif "all" in textures_source:
            iso_top_path = textures_source["all"]
        elif "texture" in textures_source:  # Simple generic (Button)
            iso_top_path = textures_source["texture"]
        elif "round" in textures_source: # Grindstone
            iso_top_path = textures_source["round"]
        elif textures_source:
            # General fallback if 'top' key is missing, use the first texture found
            iso_top_path = next(iter(textures_source.values()))


        # B. Determine the Isometric SIDE face (Priority: side > all > texture)
        if "side" in textures_source:
            iso_side_path = textures_source["side"]
        elif "all" in textures_source:  # Uniform
            iso_side_path = textures_source["all"]
        elif "texture" in textures_source:  # Simple generic
            iso_side_path = textures_source["texture"]
        elif "pattern" in textures_source: # Glazed Terracotta
            iso_side_path = textures_source["pattern"]

        # C. Fallback: If no side texture is found, use the top texture (e.g., "top" only blocks)
        if iso_side_path is None:
            iso_side_path = iso_top_path
        
        # D. Final Fallback (if top wasn't defined but side was)
        if iso_top_path is None and iso_side_path is not None:
             iso_top_path = iso_side_path


    # --- STEP 3: Apply final format and handle masking (None) ---
    
    # Isometric TOP face
    if iso_top_path:
        texture_top_name = iso_top_path.split("/")[-1]
        texture["top"] = f"{texture_top_name}_top.webp"
    else:
        # If path is None, the face is masked/should not be rendered.
        texture["top"] = None 

    # Isometric SIDE/LEFT face
    if iso_side_path:
        texture_left_name = iso_side_path.split("/")[-1]
        texture["left"] = f"{texture_left_name}_left.webp"
    else:
        # If path is None, the face is masked/should not be rendered.
        texture["left"] = None 

    images = get_images(texture)

    return images

def get_colors(id: str, namespace: str, biome: str) -> str:
    color_json_path = f"resources/json/colors/biome_tint_map.json"
    fullname = namespace + ":" + id

    with open(color_json_path, 'r') as f:
        colors_data = json.load(f)

    if fullname in colors_data.keys():
        type = colors_data[fullname]
        downfall, temperature = get_biomes_values(biome)

        if type == 'grass':
            downfall_effectiveness = downfall * temperature
            img_path = f"resources/images/colors/grass.png"
        else:
            downfall_effectiveness = downfall
            img_path = f"resources/images/colors/foliage.png"

        img = Image.open(img_path)
        x = int((1 - temperature) * 255)
        y = int((1 - downfall_effectiveness) * 255)

        x = max(0, min(255, x))
        y = max(0, min(255, y))

        r, g, b = img.getpixel((x, y))
        hex = "#{:02X}{:02X}{:02X}".format(r, g, b)
        return hex
    