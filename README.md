# OrbisPanora API

FastAPI backend for the OrbisPanora isometric Minecraft world viewer.

## 🔧 Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python run.py
```

---


## 📋 Features to Implement

### **1. Configuration & Infrastructure**
- **FastAPI base structure** (main.py, routers, models, config)
- **CORS** for Angular frontend
- **Minecraft world connection management** (singleton World instance)
- **Environment variables** (world path, port, etc.)
- **Structured logging**

### **2. Main Endpoints**

#### **A. World Metadata**
```
GET /api/world/info
```
- Returns: dimension, bounds, loaded regions, cache stats
- Uses: `world.get_world_info()`

#### **B. Chunk Data** (PRIORITY for viewer)
```
GET /api/chunk/{chunk_x}/{chunk_z}?mode=heightmap
```
- Modes: `heightmap`, `surface`, `simplified`, `full`
- Uses: `world.get_chunk_data(cx, cz, mode)`
- **Heightmap**: ~1KB (minimap, initial load)
- **Surface**: ~10-50KB (isometric rendering)

#### **C. Area Heightmap**
```
GET /api/heightmap/area?x1=0&z1=0&x2=100&z2=100
```
- For large views
- Uses: `world.get_area_heightmap(x1, z1, x2, z2)`

#### **D. Tile System** (progressive loading)
```
GET /api/tile/{tile_x}/{tile_z}?size=16
```
- Tile = 16x16 chunks by default (256x256 blocks)
- Uses: `world.get_tile_data(tx, tz, tile_size)`

#### **E. Individual Block**
```
GET /api/block/{x}/{y}/{z}
```
- For specific details
- Uses: `world.get_block(x, y, z).to_dict()`

#### **F. Biome**
```
GET /api/biome/{x}/{y}/{z}
```
- Biome information
- Uses: `world.get_biome(x, y, z)`

### **3. Optimizations & Performance**

#### **Cache System**
- **Redis** (production) or **in-memory** (dev)
- Cache by type:
  - Heightmaps (TTL: 5 min)
  - Surface blocks (TTL: 2 min)
  - Simplified chunks (TTL: 10 min)
- Invalidation on modification

#### **Rate Limiting**
- Limit requests per IP
- Prevent server overload

#### **Compression**
- Gzip for JSON responses
- ~60-70% size reduction

### **4. Error Handling**

```python
- 404: Chunk/Block not found
- 400: Invalid parameters
- 500: Server error
- 503: World not loaded
```

Standardized response format:
```json
{
  "status": "success|error",
  "data": {...},
  "error": "message",
  "timestamp": "ISO8601"
}
```

### **5. Documentation**

- **Swagger UI** automatic (`/docs`)
- **ReDoc** (`/redoc`)
- Request examples
- Pydantic schemas

### **6. Testing**

- **Unit tests**: each endpoint
- **Integration tests**: complete flows
- **Performance tests**: response time
- **Mock data** for CI/CD

### **7. Advanced Features** (optional)

#### **WebSocket** (real-time)
```
WS /api/ws/updates
```
- Modification notifications
- Chunk streaming

#### **Batch Requests**
```
POST /api/batch/chunks
Body: {"chunks": [[0,0], [0,1], [1,0]]}
```
- Load multiple chunks in one request

#### **Block Filters**
```
GET /api/chunk/{cx}/{cz}/surface?blocks=grass_block,stone
```
- Return only specific block types

### **8. Monitoring**

- **Health check**: `GET /health`
- **Metrics**: request count, average time, cache hit rate
- **Prometheus** compatible (optional)

---

## 🎯 Recommended Implementation Order

1. ✅ **Base structure** (main.py, config, CORS)
2. ✅ **Endpoint /world/info** (simple, test connection)
3. ✅ **Endpoint /chunk with heightmap mode** (essential for viewer)
4. ✅ **Endpoint /chunk with surface mode** (isometric rendering)
5. ✅ **In-memory cache** (performance)
6. ✅ **Error handling** (robustness)
7. ✅ **Endpoint /tile** (progressive loading)
8. ✅ **Endpoint /heightmap/area** (large areas)
9. ⚠️ **Tests** (quality)
10. ⚠️ **Documentation** (maintainability)

---

## 🚀 Tech Stack

- **Framework**: FastAPI
- **Python**: 3.10+
- **Library**: anvil (custom Minecraft .mca reader)
- **Cache**: Redis / in-memory
- **CORS**: for Angular frontend
- **Validation**: Pydantic
- **Documentation**: OpenAPI/Swagger

---

## 📦 Project Structure

```
api/
├── main.py                 # FastAPI app entry point
├── config.py               # Configuration & environment variables
├── requirements.txt        # Python dependencies
├── routers/
│   ├── __init__.py
│   ├── world.py           # World endpoints
│   ├── chunk.py           # Chunk endpoints
│   ├── tile.py            # Tile endpoints
│   └── block.py           # Block endpoints
├── models/
│   ├── __init__.py
│   ├── responses.py       # Response schemas
│   └── requests.py        # Request schemas
├── services/
│   ├── __init__.py
│   ├── world_service.py   # World management
│   └── cache_service.py   # Cache management
├── utils/
│   ├── __init__.py
│   ├── errors.py          # Custom exceptions
│   └── logger.py          # Logging configuration
└── tests/
    ├── __init__.py
    ├── test_world.py
    ├── test_chunk.py
    └── test_tile.py
```

---

## 📚 API Documentation

Once running, access:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 🎮 Target

- **Minecraft Version**: 1.21.1
- **Frontend**: Angular + Three.js
- **Rendering**: Isometric 2.5D
- **Textures**: `../assets/minecraft/textures/block/`

---

## 📝 Notes

- This API uses the custom `anvil` library with API-friendly methods
- All endpoints return JSON in standardized format
- Cache is essential for performance with large worlds
- CORS must be configured for Angular frontend
