"""
Mock IoT device server for testing the executor.

Run: uvicorn mock_devices:app --port 8001
All endpoints from comprehensive_scenarios.md are simulated here.
"""

import random
import asyncio
import json
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Mock IoT Device Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Configuration ────────────────────────────────────────────────

# Override specific endpoint responses (set via /config)
_response_overrides: dict = {}
# Forced failure endpoints
_failing_endpoints: set = set()
# Simulated delay range (ms)
_delay_range = (50, 300)
# 1x1 PNG placeholder so camera/VLM flows can exercise image ingestion locally.
_SAMPLE_CAMERA_IMAGE_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


@app.post("/config/delay")
async def set_delay(min_ms: int = 50, max_ms: int = 300):
    global _delay_range
    _delay_range = (min_ms, max_ms)
    return {"delay_range": _delay_range}


@app.post("/config/fail")
async def set_failing(path: str, fail: bool = True):
    if fail:
        _failing_endpoints.add(path)
    else:
        _failing_endpoints.discard(path)
    return {"failing_endpoints": list(_failing_endpoints)}


@app.post("/config/override")
async def set_override(path: str, response: dict):
    _response_overrides[path] = response
    return {"overrides": _response_overrides}


@app.post("/config/reset")
async def reset_config():
    global _delay_range
    _response_overrides.clear()
    _failing_endpoints.clear()
    _delay_range = (50, 300)
    return {"status": "reset"}


# ─── Catch-all device handler ────────────────────────────────────

async def _simulate_delay():
    delay_ms = random.randint(_delay_range[0], _delay_range[1])
    await asyncio.sleep(delay_ms / 1000)


def _make_response(path: str, body: dict, defaults: dict) -> dict:
    """Return override if set, otherwise merge body with defaults."""
    if path in _response_overrides:
        return _response_overrides[path]
    return {**defaults, "received_args": body, "timestamp": datetime.now().isoformat()}


# ═══════════════════════════════════════════════════════════════════
# SMART HOME
# ═══════════════════════════════════════════════════════════════════

@app.post("/home/bed/curtains/open")
async def curtains_open(request: Request):
    await _simulate_delay()
    return _make_response("/home/bed/curtains/open", await _safe_json(request), {"status": "open", "device": "Bedroom Curtains"})

@app.post("/home/bed/curtains/close")
async def curtains_close(request: Request):
    await _simulate_delay()
    return _make_response("/home/bed/curtains/close", await _safe_json(request), {"status": "closed", "device": "Bedroom Curtains"})

@app.post("/home/bed/curtains/set")
async def curtains_set(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/home/bed/curtains/set", body, {"status": "set", "percentage": body.get("percentage", 50), "device": "Bedroom Curtains"})

@app.post("/home/kitchen/coffee/brew")
async def coffee_brew(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/home/kitchen/coffee/brew", body, {"status": "brewing", "type": body.get("type", "regular"), "cups": body.get("cups", 1)})

@app.post("/home/kitchen/coffee/on")
async def coffee_on(request: Request):
    await _simulate_delay()
    return _make_response("/home/kitchen/coffee/on", await _safe_json(request), {"status": "on", "device": "Coffee Machine"})

@app.post("/home/kitchen/coffee/off")
async def coffee_off(request: Request):
    await _simulate_delay()
    return _make_response("/home/kitchen/coffee/off", await _safe_json(request), {"status": "off", "device": "Coffee Machine"})

@app.post("/home/hvac/set")
async def hvac_set(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/home/hvac/set", body, {"status": "set", "temp": body.get("temp", 22)})

@app.post("/home/hvac/mode")
async def hvac_mode(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/home/hvac/mode", body, {"status": "mode_set", "mode": body.get("mode", "cool")})

@app.post("/home/hvac/fan")
async def hvac_fan(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/home/hvac/fan", body, {"status": "fan_set", "state": body.get("state", "auto")})

@app.post("/home/living/speaker/play")
async def speaker_play(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/home/living/speaker/play", body, {"status": "playing", "playlist": body.get("playlist", "Default")})

@app.post("/home/living/speaker/volume")
async def speaker_volume(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/home/living/speaker/volume", body, {"status": "volume_set", "level": body.get("level", 50)})

@app.post("/home/living/speaker/stop")
async def speaker_stop(request: Request):
    await _simulate_delay()
    return _make_response("/home/living/speaker/stop", await _safe_json(request), {"status": "stopped"})

@app.post("/home/living/light/on")
async def light_on(request: Request):
    await _simulate_delay()
    return _make_response("/home/living/light/on", await _safe_json(request), {"status": "on", "device": "Living Room Light"})

@app.post("/home/living/light/off")
async def light_off(request: Request):
    await _simulate_delay()
    return _make_response("/home/living/light/off", await _safe_json(request), {"status": "off", "device": "Living Room Light"})

@app.post("/home/living/light/dim")
async def light_dim(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/home/living/light/dim", body, {"status": "dimmed", "percentage": body.get("percentage", 50)})

@app.post("/home/living/light/color")
async def light_color(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/home/living/light/color", body, {"status": "color_set", "hex": body.get("hex", "#FFFFFF")})

@app.post("/home/front/lock")
async def front_lock(request: Request):
    await _simulate_delay()
    return _make_response("/home/front/lock", await _safe_json(request), {"status": "locked", "device": "Front Door Lock"})

@app.post("/home/front/unlock")
async def front_unlock(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/home/front/unlock", body, {"status": "unlocked", "code": body.get("code", "****")})

@app.get("/home/front/status")
async def front_status(request: Request):
    await _simulate_delay()
    return _make_response("/home/front/status", {}, {"status": "locked", "device": "Front Door Lock"})

@app.post("/home/garage/open")
async def garage_open(request: Request):
    await _simulate_delay()
    return _make_response("/home/garage/open", await _safe_json(request), {"status": "open", "device": "Garage Door"})

@app.post("/home/garage/close")
async def garage_close(request: Request):
    await _simulate_delay()
    return _make_response("/home/garage/close", await _safe_json(request), {"status": "closed", "device": "Garage Door"})

@app.post("/home/cam/record")
async def cam_record(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/home/cam/record", body, {"status": "recording", "duration": body.get("duration", 30)})

@app.post("/home/cam/pan")
async def cam_pan(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/home/cam/pan", body, {"status": "panned", "angle": body.get("angle", 0)})

@app.post("/home/cam/snap")
async def cam_snap(request: Request):
    await _simulate_delay()
    return _make_response("/home/cam/snap", await _safe_json(request), {
        "status": "snapshot_taken",
        "file": "/tmp/snap_001.jpg",
        "image_base64": _SAMPLE_CAMERA_IMAGE_BASE64,
        "mime_type": "image/png",
    })


# ═══════════════════════════════════════════════════════════════════
# INDUSTRIAL MANUFACTURING
# ═══════════════════════════════════════════════════════════════════

@app.post("/factory/press/start")
async def press_start(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/factory/press/start", body, {"status": "started", "pressure": body.get("pressure", 100)})

@app.post("/factory/press/stop")
async def press_stop(request: Request):
    await _simulate_delay()
    return _make_response("/factory/press/stop", await _safe_json(request), {"status": "stopped"})

@app.post("/factory/press/estop")
async def press_estop(request: Request):
    await _simulate_delay()
    return _make_response("/factory/press/estop", await _safe_json(request), {"status": "emergency_stopped"})

@app.post("/factory/fan/set")
async def fan_set(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/factory/fan/set", body, {"status": "speed_set", "rpm": body.get("rpm", 1000)})

@app.post("/factory/fan/oscillate")
async def fan_oscillate(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/factory/fan/oscillate", body, {"status": "oscillation_set", "enabled": body.get("enabled", True)})

@app.get("/factory/sensor/temp")
async def sensor_temp(request: Request):
    await _simulate_delay()
    temp_value = _response_overrides.get("/factory/sensor/temp", {}).get("temp", round(random.uniform(20, 40), 1))
    return {"temp": temp_value, "unit": "celsius", "timestamp": datetime.now().isoformat()}

@app.post("/factory/sensor/calibrate")
async def sensor_calibrate(request: Request):
    await _simulate_delay()
    return _make_response("/factory/sensor/calibrate", await _safe_json(request), {"status": "calibrated"})

@app.post("/factory/light/flash")
async def factory_light_flash(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/factory/light/flash", body, {"status": "flashing", "color": body.get("color", "red"), "duration": body.get("duration", 10)})

@app.post("/factory/light/solid")
async def factory_light_solid(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/factory/light/solid", body, {"status": "solid", "color": body.get("color", "green")})

@app.post("/factory/light/off")
async def factory_light_off(request: Request):
    await _simulate_delay()
    return _make_response("/factory/light/off", await _safe_json(request), {"status": "off"})

@app.post("/factory/conveyor/start")
async def conveyor_start(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/factory/conveyor/start", body, {"status": "running", "speed": body.get("speed", 50)})

@app.post("/factory/conveyor/stop")
async def conveyor_stop(request: Request):
    await _simulate_delay()
    return _make_response("/factory/conveyor/stop", await _safe_json(request), {"status": "stopped"})

@app.post("/factory/conveyor/reverse")
async def conveyor_reverse(request: Request):
    await _simulate_delay()
    return _make_response("/factory/conveyor/reverse", await _safe_json(request), {"status": "reversed"})

@app.post("/factory/arm/move")
async def arm_move(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/factory/arm/move", body, {"status": "moved", "position": {"x": body.get("x", 0), "y": body.get("y", 0), "z": body.get("z", 0)}})

@app.post("/factory/arm/grip")
async def arm_grip(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/factory/arm/grip", body, {"status": "gripping", "force": body.get("force", 50)})

@app.post("/factory/arm/release")
async def arm_release(request: Request):
    await _simulate_delay()
    return _make_response("/factory/arm/release", await _safe_json(request), {"status": "released"})

@app.post("/factory/siren/alert")
async def siren_alert(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/factory/siren/alert", body, {"status": "alerting", "level": body.get("level", "warning")})

@app.post("/factory/siren/silence")
async def siren_silence(request: Request):
    await _simulate_delay()
    return _make_response("/factory/siren/silence", await _safe_json(request), {"status": "silenced"})

@app.post("/factory/cam/inspect")
async def factory_cam_inspect(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/factory/cam/inspect", body, {
        "status": "inspecting",
        "mode": body.get("mode", "standard"),
        "defects_found": 0,
        "image_base64": _SAMPLE_CAMERA_IMAGE_BASE64,
        "mime_type": "image/png",
    })

@app.post("/factory/cam/zoom")
async def factory_cam_zoom(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/factory/cam/zoom", body, {"status": "zoomed", "level": body.get("level", 1.0)})


# ═══════════════════════════════════════════════════════════════════
# SMART HOSPITAL
# ═══════════════════════════════════════════════════════════════════

@app.post("/hospital/bed/head")
async def bed_head(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/hospital/bed/head", body, {"status": "adjusted", "angle": body.get("angle", 30)})

@app.post("/hospital/bed/feet")
async def bed_feet(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/hospital/bed/feet", body, {"status": "adjusted", "angle": body.get("angle", 0)})

@app.post("/hospital/bed/height")
async def bed_height(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/hospital/bed/height", body, {"status": "adjusted", "cm": body.get("cm", 50)})

@app.post("/hospital/iv/set")
async def iv_set(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/hospital/iv/set", body, {"status": "rate_set", "ml_per_hour": body.get("ml_per_hour", 40)})

@app.post("/hospital/iv/stop")
async def iv_stop(request: Request):
    await _simulate_delay()
    return _make_response("/hospital/iv/stop", await _safe_json(request), {"status": "stopped"})

@app.post("/hospital/iv/reset")
async def iv_reset(request: Request):
    await _simulate_delay()
    return _make_response("/hospital/iv/reset", await _safe_json(request), {"status": "alarm_reset"})

@app.post("/hospital/lights/on")
async def hospital_lights_on(request: Request):
    await _simulate_delay()
    return _make_response("/hospital/lights/on", await _safe_json(request), {"status": "on"})

@app.post("/hospital/lights/off")
async def hospital_lights_off(request: Request):
    await _simulate_delay()
    return _make_response("/hospital/lights/off", await _safe_json(request), {"status": "off"})

@app.post("/hospital/lights/dim")
async def hospital_lights_dim(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/hospital/lights/dim", body, {"status": "dimmed", "percentage": body.get("percentage", 50)})

@app.post("/hospital/call/alert")
async def nurse_call_alert(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/hospital/call/alert", body, {"status": "alert_sent", "priority": body.get("priority", "normal")})

@app.post("/hospital/call/cancel")
async def nurse_call_cancel(request: Request):
    await _simulate_delay()
    return _make_response("/hospital/call/cancel", await _safe_json(request), {"status": "cancelled"})

@app.post("/hospital/monitor/bp")
async def monitor_bp(request: Request):
    await _simulate_delay()
    return _make_response("/hospital/monitor/bp", {}, {"status": "measured", "systolic": random.randint(110, 140), "diastolic": random.randint(70, 90)})

@app.post("/hospital/monitor/hr")
async def monitor_hr(request: Request):
    await _simulate_delay()
    return _make_response("/hospital/monitor/hr", {}, {"status": "measured", "bpm": random.randint(60, 100)})

@app.post("/hospital/monitor/o2")
async def monitor_o2(request: Request):
    await _simulate_delay()
    return _make_response("/hospital/monitor/o2", {}, {"status": "measured", "spo2": random.randint(94, 100)})

@app.post("/hospital/hvac/set")
async def hospital_hvac_set(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/hospital/hvac/set", body, {"status": "set", "temp": body.get("temp", 23)})

@app.post("/hospital/hvac/filter")
async def hospital_hvac_filter(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/hospital/hvac/filter", body, {"status": "filter_set", "mode": body.get("mode", "hepa")})

@app.post("/hospital/door/lock")
async def hospital_door_lock(request: Request):
    await _simulate_delay()
    return _make_response("/hospital/door/lock", await _safe_json(request), {"status": "locked"})

@app.post("/hospital/door/unlock")
async def hospital_door_unlock(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/hospital/door/unlock", body, {"status": "unlocked", "badge": body.get("badge", "***")})

@app.post("/hospital/door/open")
async def hospital_door_open(request: Request):
    await _simulate_delay()
    return _make_response("/hospital/door/open", await _safe_json(request), {"status": "emergency_opened"})

@app.post("/hospital/sanitizer/dispense")
async def sanitizer_dispense(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/hospital/sanitizer/dispense", body, {"status": "dispensed", "amount": body.get("amount", 5)})

@app.get("/hospital/sanitizer/level")
async def sanitizer_level(request: Request):
    await _simulate_delay()
    return _make_response("/hospital/sanitizer/level", {}, {"level_ml": random.randint(100, 500)})


# ═══════════════════════════════════════════════════════════════════
# SMART AGRICULTURE
# ═══════════════════════════════════════════════════════════════════

@app.post("/farm/sprinkler/open")
async def sprinkler_open(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/farm/sprinkler/open", body, {"status": "open", "duration": body.get("duration", 30)})

@app.post("/farm/sprinkler/close")
async def sprinkler_close(request: Request):
    await _simulate_delay()
    return _make_response("/farm/sprinkler/close", await _safe_json(request), {"status": "closed"})

@app.get("/farm/sensor/moisture")
async def sensor_moisture(request: Request):
    await _simulate_delay()
    return _make_response("/farm/sensor/moisture", {}, {"moisture": round(random.uniform(20, 80), 1), "unit": "percent"})

@app.get("/farm/sensor/ph")
async def sensor_ph(request: Request):
    await _simulate_delay()
    return _make_response("/farm/sensor/ph", {}, {"ph": round(random.uniform(5.5, 7.5), 1)})

@app.get("/farm/sensor/temp")
async def farm_sensor_temp(request: Request):
    await _simulate_delay()
    return _make_response("/farm/sensor/temp", {}, {"temp": round(random.uniform(15, 35), 1), "unit": "celsius"})

@app.post("/farm/roof/open")
async def roof_open(request: Request):
    body = await _safe_json(request)
    await _simulate_delay()
    return _make_response("/farm/roof/open", body, {"status": "open", "percentage": body.get("percentage", 100)})

@app.post("/farm/roof/close")
async def roof_close(request: Request):
    await _simulate_delay()
    return _make_response("/farm/roof/close", await _safe_json(request), {"status": "closed"})


# ═══════════════════════════════════════════════════════════════════
# SSE SENSOR STREAMS
# ═══════════════════════════════════════════════════════════════════

@app.get("/factory/sensor/temp/stream")
async def factory_temp_stream():
    """Streams factory floor temperature every 2 seconds.
    Mostly 20-35°C; spikes to 36-45°C ~15% of the time to simulate overheating."""
    async def generate():
        while True:
            if random.random() < 0.15:
                temp = round(random.uniform(36.0, 45.0), 1)   # overheating spike
            else:
                temp = round(random.uniform(20.0, 35.0), 1)
            event = {"temp": temp, "unit": "celsius", "timestamp": datetime.now().isoformat()}
            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(2)
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/farm/sensor/moisture/stream")
async def farm_moisture_stream():
    """Streams soil moisture every 3 seconds.
    Mostly 40-70%; drops below 30% ~15% of the time to simulate dry soil."""
    async def generate():
        while True:
            if random.random() < 0.15:
                moisture = round(random.uniform(10.0, 29.9), 1)   # dry soil
            else:
                moisture = round(random.uniform(40.0, 70.0), 1)
            event = {"moisture": moisture, "unit": "percent", "timestamp": datetime.now().isoformat()}
            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(3)
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/home/motion/stream")
async def home_motion_stream():
    """Streams motion sensor events every 2 seconds.
    Mostly no motion; detects motion ~20% of the time across random zones."""
    _zones = ["living_room", "hallway", "kitchen", "front_door", "backyard"]
    async def generate():
        while True:
            detected = random.random() < 0.20
            event = {
                "motion": detected,
                "zone": random.choice(_zones) if detected else None,
                "timestamp": datetime.now().isoformat(),
            }
            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(2)
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/hospital/monitor/vitals/stream")
async def hospital_vitals_stream():
    """Streams patient vitals every 2 seconds.
    Heart rate 60-100 bpm; SpO2 94-100%. Occasional out-of-range values (~10%)."""
    async def generate():
        while True:
            if random.random() < 0.10:
                heart_rate = random.randint(101, 130)   # tachycardia
                spo2 = random.randint(88, 93)           # low oxygen
            else:
                heart_rate = random.randint(60, 100)
                spo2 = random.randint(95, 100)
            event = {
                "heart_rate": heart_rate,
                "spo2": spo2,
                "timestamp": datetime.now().isoformat(),
            }
            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(2)
    return StreamingResponse(generate(), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# CATCH-ALL (for any endpoint not explicitly defined)
# ═══════════════════════════════════════════════════════════════════

@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def catch_all(full_path: str, request: Request):
    """Catch-all: simulates any device endpoint not explicitly defined."""
    path = f"/{full_path}"
    await _simulate_delay()

    if path in _failing_endpoints:
        return {"error": "Simulated failure", "device": full_path}, 500

    body = await _safe_json(request)
    return _make_response(path, body, {"status": "ok", "path": path, "method": request.method})


# ─── Utility ──────────────────────────────────────────────────────

async def _safe_json(request: Request) -> dict:
    """Safely parse JSON body, returning {} on failure."""
    try:
        return await request.json()
    except Exception:
        return {}
