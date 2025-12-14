"""
World service for managing Minecraft world instance.
Singleton pattern to ensure only one World instance is loaded.
"""

from typing import Optional
from models.responses import WorldInfoResponse, ChunkDataResponse, AreaHeightmapResponse, TileDataResponse, BlockDataResponse, BiomeDataResponse
from anvil import World
from config import settings
import os
import zipfile
import tempfile
import shutil


class WorldService:
    """Singleton service for managing Minecraft world."""
    
    _instance: Optional['WorldService'] = None
    _world: Optional[World] = None
    _world_path: Optional[str] = None
    
    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super(WorldService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize world service."""
        # Temporarily skip world loading to test API connectivity
        # if self._world is None:
        #     self._load_world()
        pass
    
    def _load_world(self):
        """Load the Minecraft world."""
        try:
            print(f"Loading world from: {settings.world_path}")
            self._world = World(
                settings.world_path,
                dimension=settings.world_dimension
            )
            self._world_path = settings.world_path
            print(f"World loaded successfully")
        except Exception as e:
            print(f"Failed to load world: {e}")
            raise
    
    @property
    def world(self) -> World:
        """Get the world instance with lazy loading."""
        if self._world is None:
            self._load_world()
        return self._world
    
    @property
    def world_path(self) -> Optional[str]:
        """Get the path to the currently loaded world."""
        return self._world_path
    
    def load_world_from_path(self, world_path: str, dimension: str = None):
        """
        Load a world from a specific path.
        
        Args:
            world_path: Path to the world directory
            dimension: Dimension to load (defaults to settings.world_dimension)
        """
        try:
            if dimension is None:
                dimension = settings.world_dimension
            
            print(f"Loading world from: {world_path} (dimension: {dimension})")
            self._world = World(
                world_path,
                dimension=dimension
            )
            self._world_path = world_path
            print(f"World loaded successfully from {world_path}")
            print(f"[WorldService] World instance updated: {self._world is not None}")
        except Exception as e:
            print(f"Failed to load world from {world_path}: {e}")
            raise
    
    def load_world_from_zip(self, zip_path: str, dimension: str = None):
        """
        Extract a zip file containing a Minecraft world and load it.
        
        Args:
            zip_path: Path to the zip file
            dimension: Dimension to load (defaults to settings.world_dimension)
        
        Returns:
            Path to the extracted world directory
        """
        try:
            # Validate zip file
            if not zipfile.is_zipfile(zip_path):
                raise ValueError(f"File is not a valid zip file: {zip_path}")
            
            # Check file size
            file_size = os.path.getsize(zip_path)
            max_size = settings.upload_max_size_mb * 1024 * 1024
            if file_size > max_size:
                raise ValueError(f"Zip file too large ({file_size} bytes). Maximum allowed: {max_size} bytes")
            
            # Create temp directory for extraction
            os.makedirs(settings.temp_world_dir, exist_ok=True)
            temp_dir = tempfile.mkdtemp(dir=settings.temp_world_dir)
            
            print(f"Extracting world from {zip_path} to {temp_dir}")
            
            # Extract zip file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Find the world directory (could be at root or in a subdirectory)
            world_dir = self._find_world_directory(temp_dir)
            if not world_dir:
                raise ValueError("No valid Minecraft world found in the zip file")
            
            print(f"Found world directory: {world_dir}")
            
            # Load the world
            self.load_world_from_path(world_dir, dimension)
            
            # Clean up old temp worlds if needed
            if settings.cleanup_temp_files:
                self._cleanup_old_temp_worlds()
            
            return world_dir
            
        except Exception as e:
            # Clean up temp directory on failure
            if 'temp_dir' in locals():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise
    
    def _find_world_directory(self, base_path: str) -> Optional[str]:
        """
        Find the Minecraft world directory within the extracted zip.
        Looks for a directory containing 'session.lock' or 'level.dat'.
        """
        for root, dirs, files in os.walk(base_path):
            # Check if this directory contains world files
            if 'level.dat' in files or 'session.lock' in files:
                # Make sure it has a region directory (for overworld)
                region_path = os.path.join(root, 'region')
                if os.path.exists(region_path) and os.path.isdir(region_path):
                    return root
        
        # If not found, check if the base_path itself is a world directory
        if os.path.exists(os.path.join(base_path, 'level.dat')):
            return base_path
            
        return None
    
    def _cleanup_old_temp_worlds(self):
        """Clean up old temporary world directories."""
        try:
            if not os.path.exists(settings.temp_world_dir):
                return
                
            temp_dirs = [d for d in os.listdir(settings.temp_world_dir) 
                        if os.path.isdir(os.path.join(settings.temp_world_dir, d))]
            
            if len(temp_dirs) > settings.max_temp_worlds:
                # Sort by modification time (oldest first)
                temp_dirs.sort(key=lambda d: os.path.getmtime(os.path.join(settings.temp_world_dir, d)))
                
                # Remove oldest directories
                dirs_to_remove = temp_dirs[:-settings.max_temp_worlds]
                for dir_name in dirs_to_remove:
                    dir_path = os.path.join(settings.temp_world_dir, dir_name)
                    print(f"Cleaning up old temp world: {dir_path}")
                    shutil.rmtree(dir_path, ignore_errors=True)
                    
        except Exception as e:
            print(f"Error during cleanup: {e}")
    
    def get_world_info(self) -> dict:
        """Get world information using the library's method."""
        try:
            world_info_dict = self.world.get_world_info()
            if not world_info_dict:
                return None
            
            # Map anvil library fields to our response model
            mapped_info = {
                "dimension": world_info_dict.get("dimension", "overworld"),
                "world_folder": world_info_dict.get("world_folder", ""),
                "region_dir": world_info_dict.get("region_dir", ""),
                "bounds": world_info_dict.get("bounds"),
                "loaded_regions": world_info_dict.get("loaded_regions", 0),
                "region_list": world_info_dict.get("region_coordinates", []),
                "cache_stats": {
                    "cache_enabled": world_info_dict.get("cache_enabled", False),
                    "chunk_cache_size": world_info_dict.get("chunk_cache_size", 0),
                    "region_cache_size": world_info_dict.get("region_cache_size", 0)
                } if world_info_dict.get("cache_enabled") else None
            }
            
            return WorldInfoResponse(**mapped_info)
        except Exception as e:
            print(f"Error getting world info: {e}")
            return None
    
    def is_loaded(self) -> bool:
        """Check if world is loaded without triggering loading."""
        return self._world is not None
    
    def get_chunk_data(self, chunk_x: int, chunk_z: int, chunk_h: int = 0, mode: str = 'heightmap'):
        """
        Get chunk data in various formats.
        
        Args:
            chunk_x: Chunk X coordinate
            chunk_z: Chunk Z coordinate
            mode: Data format ('heightmap', 'surface', 'isometric', 'simplified', 'full')
        
        Returns:
            ChunkDataResponse object or None if chunk not found
        """
        try:
            chunk = self.world.get_chunk(chunk_x, chunk_z)
            if chunk is None:
                return None
            
            if mode == "heightmap":
                # Get heightmap (topmost solid blocks)
                heightmap = []
                for z in range(16):
                    height_row = []
                    for x in range(16):
                        # Find the highest solid block
                        height = 0
                        for y in range(320, -64, -1):  # From top to bottom
                            try:
                                block = chunk.get_block(x, y, z)
                                if block and block.name() not in ['minecraft:air', 'minecraft:cave_air', 'minecraft:void_air']:
                                    height = y
                                    break
                            except:
                                continue
                        height_row.append(height)
                    heightmap.append(height_row)
                
                return ChunkDataResponse(
                    chunk_x=chunk_x,
                    chunk_z=chunk_z,
                    heightmap=heightmap,
                    surface_blocks=None,
                    sections=None,
                    palette=None
                )
            
            elif mode == "surface":
                # Get surface blocks with biomes
                surface_blocks = []
                for z in range(16):
                    for x in range(16):
                        # Find the topmost solid block
                        for y in range(320, -64, -1):
                            try:
                                block = chunk.get_block(x, y, z)
                                if block and block.name() not in ['minecraft:air', 'minecraft:cave_air', 'minecraft:void_air']:
                                    # Get biome at this position
                                    global_x = chunk_x * 16 + x
                                    global_z = chunk_z * 16 + z
                                    biome = self.world.get_biome(global_x, y, global_z)
                                    
                                    surface_blocks.append({
                                        "x": global_x,
                                        "y": y,
                                        "z": global_z,
                                        "block": block.name(),
                                        "biome": biome.name() if biome else "unknown"
                                    })
                                    break
                            except:
                                continue
                
                return ChunkDataResponse(
                    chunk_x=chunk_x,
                    chunk_z=chunk_z,
                    heightmap=None,
                    surface_blocks=surface_blocks,
                    sections=None,
                    palette=None
                )
            
            # changais par simoni
            # pour afficher un chunk a la fois
            elif mode == "isometric":
                isometric_blocks = []
                min_value = 320
                max_value = -64

                AIR = ['minecraft:air', 'minecraft:cave_air', 'minecraft:void_air']
                INVISIBLE = ['minecraft:acacia_leaves', 'minecraft:azalea_leaves', 'minecraft:bamboo_large_leaves', 'minecraft:bamboo_small_leaves', 
                              'minecraft:birch_leaves', 'minecraft:cherry_leaves', 'minecraft:dark_oak_leaves', 
                              'minecraft:flowering_azalea_leaves', 'minecraft:jungle_leaves', 'minecraft:mangrove_leaves',
                              'minecraft:oak_leaves', 'minecraft:spruce_leaves', 'minecraft:glass', 'minecraft:water', 
                              'minecraft:ice', 'minecraft:tall_grass', 'minecraft:grass', 'minecraft:short_grass',
                              'minecraft:fern', 'minecraft:large_fern', 'minecraft:vine', 'minecraft:torch']
                # TODO: ajouter vine, staires, grass, flowers, etc

                global_biome_x = chunk_x * 16
                global_biome_z = chunk_z * 16
                global_chunk_x = abs(global_biome_x)
                global_chunk_z = abs(global_biome_z)

                Matrix1D = []
                Matrix2D = []
                Matrix3D = []
                
                # First pass: finde lowest surface block89- 77
                for z in range(16):
                    for x in range(16):
                        # Find the highest solid block (surface)
                        for y in range(320, -65, -1):
                            try:
                                block = chunk.get_block(x, y, z)
                                if block:

                                    if block.name() not in INVISIBLE:
                                        # heightmap[z][x] = y
                                        if y < min_value:
                                            min_value = y
                                    if block.name() not in AIR:
                                        if y> max_value:
                                            max_value = y
                                        break
                            except:
                                continue
                
                print("min", min_value, "max", max_value) ## est ce quil faut prendre max valeu ou pas ??

                # for z in range(16):
                #     for x in range(16):
                #         for y in range(min_value, max_value+1, 1): # 77 ... 89
                #             # 89 ... 77 +1
                #             try:
                #                 # trouver un meilleur facon pour eviter de appeller block 2e fois
                #                 block = chunk.get_block(x, y, z)
                #             except:
                #                 Matrix1D.append("0")
                #                 continue

                #             if block and block.name() not in AIR:
                #                 Matrix1D.append(block.name().split(":")[1])
                #             else:
                #                 Matrix1D.append("0")

                #         Matrix2D.append(Matrix1D)
                #         Matrix1D=[]
                #     Matrix3D.append(Matrix2D)
                #     Matrix2D=[]

                # print("la famu matrix",len(Matrix3D))
                # print("la famu matrix", len(Matrix3D[0]))
                # print("la famu matrix", len(Matrix3D[0][0]))
                # # a mettre en place side
                # #print(Matrix3D)
                # side = 0
                cpt = 0

                # for z in range(len(Matrix3D)):
                #     for x in range(len(Matrix3D[z])):
                #         for y in range(min_value, max_value+1, 1):
                #             y_index = y-min_value # peut etre verifier si out of range 77 -
                #             #print("test0", y_index)
                #             block = Matrix3D[z][x][y_index]
                #             #print("test1", y_index)
                #             if block != 0:
                #                 for depth_y in range(y, max_value+1, 1): # 89 ... 77
                #                     # 
                #                     y_index = depth_y - min_value # peut etre verifier si out of range
                #                     #print("test10", y_index)
                #                     block = Matrix3D[z][x][y_index]
                #                     #print("test20", y_index)
                #                     if block != 0:
                #                         global_x = global_biome_x + x
                #                         global_z = global_biome_z + z
                #                         # biome = self.world.get_biome(global_x, depth_y, global_z)

                #                         
                #                         j=abs(abs(global_z) - global_chunk_z)
                #                         k=abs(abs(depth_y) - abs(min_value)) # height coeficient for render order

                #                         x_final = 16 * (i - j)
                #                         y_final = 8*(i+j) - 16*k
                #                         x_final = round(x_final * 100) / 100
                #                         y_final = round(y_final * 100) / 100

                #                         #print("TEST")
                #                         block_name = block.name().split(":")[1]
                #                         isometric_blocks.append([block_name+".webp", x_final, y_final])
                #                         cpt +=1
                #                 break

                
                # second pass: select all blocks from max height and lowest surface
                for z in range(16):
                    for x in range(16):
                        for y in range(min_value, max_value+1, 1):
                            try:
                                block = chunk.get_block(x, y, z)
                                if block and block.name() not in AIR:
                                    for depth_y in range(y, max_value+1, 1):
                                        try:
                                            depth_block = chunk.get_block(x, depth_y, z)
                                            if depth_block and depth_block.name() not in AIR: # peut etre controle de tro

                                                # Get biome at this position
                                                global_x = global_biome_x + x
                                                global_z = global_biome_z + z
                                                biome = self.world.get_biome(global_x, depth_y, global_z)

                                                # i=abs(abs(global_x) - global_chunk_x)
                                                #j=abs(abs(global_z) - global_chunk_z)-60 +64 = 4
                                                #k2= min_value-chunk_h # cunk_h - min_value est mieux je crois
                                                k=abs(depth_y - min_value) # height coeficient for render order
                                                #k=k+k2

                                                # remplacer 16 et 8 par des constantes passer ou definies ailleurs
                                                # c'est sont des vectors de projection isometrique d'un block
                                                # min = -60  h = -60 -> 0
                                                # min = -61 h = -60 -> -1
                                                # 60 - 61 = -1

                                                # min = 77 h=77 -> 0
                                                # min = 79 h=77 -> -2
                                                # 77 - 79 = -2
                                                x_final = 16 * (global_x - global_z)
                                                y_final = (8*(global_x+global_z) - 16*k)+(chunk_h-min_value)*16
                                                x_final = round(x_final * 100) / 100
                                                y_final = round(y_final * 100) / 100
                                                block_name = depth_block.name().split(":")[1]
                                                isometric_blocks.append([block_name+".webp", x_final, y_final])
                                                cpt +=1

                                                # isometric_blocks.append({
                                                #     "x": x_final,
                                                #     "y": k,
                                                #     "z": y_final,
                                                #     "block": depth_block.name(),
                                                #     "properties": {str(key): str(value) for key, value in depth_block.properties.items()},
                                                #     "biome": biome.name() if biome else "unknown"
                                                # })
                                        except:
                                            continue
                                    break
                            except:
                                continue
                

                
                return ChunkDataResponse(
                    chunk_x=chunk_x,
                    chunk_z=chunk_z,
                    heightmap=cpt,
                    surface_blocks=isometric_blocks,
                    sections=None,
                    palette=min_value
                )
            
            elif mode == "render":
                # Fully optimized for 2D isometric rendering - pre-calculated positions and sprites
                render_data = self._generate_render_data(chunk_x, chunk_z)
                
                return ChunkDataResponse(
                    chunk_x=chunk_x,
                    chunk_z=chunk_z,
                    heightmap=None,
                    surface_blocks=None,
                    sections=None,
                    palette=None,
                    render_data=render_data  # Custom field for render mode
                )
                
        except Exception as e:
            print(f"Error getting chunk data: {e}")
            return None
    
    def _generate_render_data(self, chunk_x: int, chunk_z: int) -> dict:
        """
        Generate pre-calculated render data optimized for 2D isometric display.
        Simplified version focusing on surface blocks only.
        """
        try:
            chunk = self.world.get_chunk(chunk_x, chunk_z)
            if chunk is None:
                return {"blocks": [], "sprites": {}, "bounds": {"min_x": 0, "max_x": 0, "min_y": 0, "max_y": 0}}

            render_blocks = []
            sprites_needed = set()

            # Pre-calculate isometric projection constants
            # For proper isometric projection: 30-degree angle creates diamond shape
            TILE_WIDTH = 32   # pixels per tile width (match JavaScript)
            TILE_HEIGHT = 16  # pixels per tile height (half of width for isometric)
            BLOCK_HEIGHT = 12 # pixels per block height (match JavaScript)

            min_screen_x = float('inf')
            max_screen_x = float('-inf')
            min_screen_y = float('inf')
            max_screen_y = float('-inf')

            # Full optimized scan to retrieve all surface blocks
            for local_x in range(0, 16):  # Full X coverage
                for local_z in range(0, 16):
                    # Scan multiple layers for more visual details
                    surface_blocks_found = 0
                    max_surface_blocks = 3  # Maximum visible blocks per column

                    # Scan from top to bottom to find all surface blocks
                    for y in range(320, -64, -1):  # Full Minecraft height range
                        try:
                            block = chunk.get_block(local_x, y, local_z)
                            if block and block.name() not in ['minecraft:air', 'minecraft:cave_air', 'minecraft:void_air']:
                                global_x = chunk_x * 16 + local_x
                                global_z = chunk_z * 16 + local_z

                                # Get biome for this position
                                try:
                                    biome = self.world.get_biome(global_x, y, global_z)
                                    biome_name = biome.name() if biome else "plains"
                                except:
                                    biome_name = "plains"

                                # Use the actual block name
                                block_name = block.name()

                                # Calculate isometric coordinates server-side (but ignored client-side)
                                screen_x = (global_x - global_z) * (TILE_WIDTH / 2)
                                screen_y = (global_x + global_z) * (TILE_HEIGHT / 2) - y * BLOCK_HEIGHT

                                # Update bounds
                                min_screen_x = min(min_screen_x, screen_x)
                                max_screen_x = max(max_screen_x, screen_x + TILE_WIDTH)
                                min_screen_y = min(min_screen_y, screen_y)
                                max_screen_y = max(max_screen_y, screen_y + BLOCK_HEIGHT)

                                render_blocks.append({
                                    "screen_x": screen_x,  # Kept for compatibility but ignored client-side
                                    "screen_y": screen_y,  # Kept for compatibility but ignored client-side
                                    "world_x": global_x,
                                    "world_y": y,
                                    "world_z": global_z,
                                    "block": block_name,
                                    "biome": biome_name,
                                    "sprite": self._get_sprite_key(block_name, biome_name),
                                    "is_surface": (surface_blocks_found == 0),  # First block = surface
                                    "depth": y
                                })

                                surface_blocks_found += 1
                                # Limit to a few blocks per column to avoid overload
                                if surface_blocks_found >= max_surface_blocks:
                                    break

                        except Exception as e:
                            # Skip individual block errors
                            continue

            # Sort blocks by depth (back to front) - now done client-side
            # render_blocks.sort(key=lambda b: b['depth'], reverse=True)

            # Generate sprite data (kept for compatibility)
            sprites_needed = set()
            for block in render_blocks:
                sprites_needed.add(block["sprite"])

            sprites = {}
            for sprite_key in sprites_needed:
                sprites[sprite_key] = self._get_sprite_data(sprite_key)

            return {
                "blocks": render_blocks,
                "sprites": sprites,
                "bounds": {
                    "min_x": min_screen_x if min_screen_x != float('inf') else 0,
                    "max_x": max_screen_x if max_screen_x != float('-inf') else 100,
                    "min_y": min_screen_y if min_screen_y != float('inf') else 0,
                    "max_y": max_screen_y if max_screen_y != float('-inf') else 100
                }
            }

        except Exception as e:
            print(f"Error generating render data for chunk ({chunk_x}, {chunk_z}): {e}")
            return {"blocks": [], "sprites": {}, "bounds": {"min_x": 0, "max_x": 0, "min_y": 0, "max_y": 0}}
    
    def _get_sprite_key(self, block_name: str, biome_name: str) -> str:
        """Generate a unique key for sprite caching based on block and biome."""
        # Simplified sprite key generation
        if block_name == "minecraft:grass_block":
            if biome_name in ["plains", "forest"]:
                return "grass_plains"
            elif biome_name in ["taiga", "snowy_taiga"]:
                return "grass_taiga"
            elif biome_name == "desert":
                return "sand"
            else:
                return "grass_default"
        elif block_name == "minecraft:stone":
            return "stone"
        elif block_name == "minecraft:dirt":
            return "dirt"
        elif block_name == "minecraft:water":
            return "water"
        elif block_name == "minecraft:sand":
            return "sand"
        elif block_name == "minecraft:oak_log":
            return "oak_log"
        elif block_name == "minecraft:oak_leaves":
            return "oak_leaves"
        else:
            return "unknown_block"
    
    def _get_sprite_data(self, sprite_key: str) -> dict:
        """Return sprite data (could be base64 image or URL to pre-generated sprite)."""
        # For now, return color data that can be used to generate CSS/styled divs
        # In production, this would return base64-encoded images or URLs
        
        sprite_colors = {
            "grass_plains": {"color": "#4CAF50", "border": "#2E7D32"},
            "grass_taiga": {"color": "#388E3C", "border": "#1B5E20"},
            "grass_default": {"color": "#4CAF50", "border": "#2E7D32"},
            "stone": {"color": "#9E9E9E", "border": "#616161"},
            "dirt": {"color": "#8D6E63", "border": "#5D4037"},
            "sand": {"color": "#FDD835", "border": "#F9A825"},
            "water": {"color": "#2196F3", "border": "#1976D2"},
            "oak_log": {"color": "#6D4C41", "border": "#4E342E"},
            "oak_leaves": {"color": "#4CAF50", "border": "#2E7D32"},
            "unknown_block": {"color": "#666666", "border": "#424242"}
        }
        
        return sprite_colors.get(sprite_key, sprite_colors["unknown_block"])
    
    def get_area_heightmap(self, x1: int, z1: int, x2: int, z2: int) -> dict:
        """
        Get heightmap for an area.
        
        Args:
            x1, z1: Minimum block coordinates
            x2, z2: Maximum block coordinates
        
        Returns:
            Area heightmap dictionary
        """
        area_heightmap_dict = self.world.get_area_heightmap(x1, z1, x2, z2)
        return AreaHeightmapResponse(**area_heightmap_dict) if area_heightmap_dict else None
    
    def get_tile_data(self, tile_x: int, tile_z: int, tile_size: int = 16) -> dict:
        """
        Get tile data for progressive loading.
        
        Args:
            tile_x: Tile X coordinate
            tile_z: Tile Z coordinate
            tile_size: Number of chunks per tile side
        
        Returns:
            Tile data dictionary with all chunks
        """
        tile_data_dict = self.world.get_tile_data(tile_x, tile_z, tile_size)
        return TileDataResponse(**tile_data_dict) if tile_data_dict else None

    def get_block_data(self, block_x: int, block_y: int, block_z: int) -> dict:
        """
        Get block data at specified coordinates.
        
        Args:
            block_x: Block X coordinate
            block_y: Block Y coordinate
            block_z: Block Z coordinate
        
        Returns:
            Block data dictionary or None if block not found
        """
        block = self.world.get_block(block_x, block_y, block_z)
        block_data_dict = {
            "block_x": block_x,
            "block_y": block_y,
            "block_z": block_z,
            "id": str(block.id),
            "properties": {str(key): str(value) for key, value in block.properties.items()}
        }
        return BlockDataResponse(**block_data_dict) if block_data_dict else None
    
    def get_biome_data(self, biome_x: int, biome_y: int, biome_z: int) -> dict:
        """
        Get biome data at specified coordinates.
        
        Args:
            biome_x: Biome X coordinate
            biome_z: Biome Z coordinate
        
        Returns:
            Biome data dictionary or None if biome not found
        """
        biome = self.world.get_biome(biome_x, biome_y, biome_z)
        biome_data_dict = {
            "biome_x": biome_x,
            "biome_y": biome_y,
            "biome_z": biome_z,
            "id": str(biome.id),
        }
        return BiomeDataResponse(**biome_data_dict) if biome_data_dict else None

_world_service: Optional[WorldService] = None


def get_world_service() -> WorldService:
    """
    Get the global WorldService instance.
    Used as a dependency in FastAPI endpoints.
    """
    global _world_service
    if _world_service is None:
        _world_service = WorldService()
    return _world_service
