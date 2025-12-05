# Comprehensive IoT Scenarios (Detailed)

This document provides 5 detailed scenarios to test the versatility of the IoT Policy Manager. Each scenario includes 8 devices with multiple capabilities and 3 distinct tasks.

---

## 1. Smart Home

### Devices
1.  **Bedroom Curtains** (Type: Curtain)
    *   `Open`: POST `http://home/bed/curtains/open` `{}`
    *   `Close`: POST `http://home/bed/curtains/close` `{}`
    *   `Set Position`: POST `http://home/bed/curtains/set` `{"percentage": "integer"}`
2.  **Coffee Machine** (Type: Appliance)
    *   `Brew`: POST `http://home/kitchen/coffee/brew` `{"type": "string", "cups": "integer"}`
    *   `Turn On`: POST `http://home/kitchen/coffee/on` `{}`
    *   `Turn Off`: POST `http://home/kitchen/coffee/off` `{}`
3.  **Thermostat** (Type: Climate)
    *   `Set Temp`: POST `http://home/hvac/set` `{"temp": "float"}`
    *   `Set Mode`: POST `http://home/hvac/mode` `{"mode": "string (cool/heat/fan)"}`
    *   `Fan Control`: POST `http://home/hvac/fan` `{"state": "string (on/auto)"}`
4.  **Smart Speaker** (Type: Speaker)
    *   `Play Music`: POST `http://home/living/speaker/play` `{"playlist": "string"}`
    *   `Set Volume`: POST `http://home/living/speaker/volume` `{"level": "integer"}`
    *   `Stop`: POST `http://home/living/speaker/stop` `{}`
5.  **Living Room Light** (Type: Light)
    *   `Turn On`: POST `http://home/living/light/on` `{}`
    *   `Turn Off`: POST `http://home/living/light/off` `{}`
    *   `Dim`: POST `http://home/living/light/dim` `{"percentage": "integer"}`
    *   `Set Color`: POST `http://home/living/light/color` `{"hex": "string"}`
6.  **Front Door Lock** (Type: Lock)
    *   `Lock`: POST `http://home/front/lock` `{}`
    *   `Unlock`: POST `http://home/front/unlock` `{"code": "string"}`
    *   `Status`: GET `http://home/front/status` `{}`
7.  **Garage Door** (Type: Door)
    *   `Open`: POST `http://home/garage/open` `{}`
    *   `Close`: POST `http://home/garage/close` `{}`
8.  **Security Camera** (Type: Camera)
    *   `Record`: POST `http://home/cam/record` `{"duration": "integer"}`
    *   `Pan`: POST `http://home/cam/pan` `{"angle": "integer"}`
    *   `Snapshot`: POST `http://home/cam/snap` `{}`

### Tasks
1.  **Morning Routine**
    > "At 7:00 AM, open the bedroom curtains to 50%, set the thermostat to 22 degrees, brew 2 cups of regular coffee, and play the 'Morning Jazz' playlist at volume 30."
2.  **Night Security**
    > "At 11:00 PM, lock the front door, close the garage door, turn off the living room light, and set the security camera to record for 60 seconds."
3.  **Party Mode**
    > "At 8:00 PM, set the living room light color to '#FF00FF', dim lights to 70%, play 'Party Hits' on the smart speaker at volume 80, and set the thermostat fan to 'on'."

---

## 2. Industrial Manufacturing

### Devices
1.  **Hydraulic Press** (Type: Machinery)
    *   `Start`: POST `http://factory/press/start` `{"pressure": "integer"}`
    *   `Stop`: POST `http://factory/press/stop` `{}`
    *   `Emergency Stop`: POST `http://factory/press/estop` `{}`
2.  **Cooling Fan** (Type: Fan)
    *   `Set Speed`: POST `http://factory/fan/set` `{"rpm": "integer"}`
    *   `Oscillate`: POST `http://factory/fan/oscillate` `{"enabled": "boolean"}`
3.  **Temp Sensor** (Type: Sensor)
    *   `Read`: GET `http://factory/sensor/temp` `{}`
    *   `Calibrate`: POST `http://factory/sensor/calibrate` `{}`
4.  **Warning Light** (Type: Light)
    *   `Flash`: POST `http://factory/light/flash` `{"color": "string", "duration": "integer"}`
    *   `Solid`: POST `http://factory/light/solid` `{"color": "string"}`
    *   `Off`: POST `http://factory/light/off` `{}`
5.  **Conveyor Belt** (Type: Motor)
    *   `Start`: POST `http://factory/conveyor/start` `{"speed": "integer"}`
    *   `Stop`: POST `http://factory/conveyor/stop` `{}`
    *   `Reverse`: POST `http://factory/conveyor/reverse` `{}`
6.  **Robotic Arm** (Type: Robot)
    *   `Move To`: POST `http://factory/arm/move` `{"x": "float", "y": "float", "z": "float"}`
    *   `Grip`: POST `http://factory/arm/grip` `{"force": "integer"}`
    *   `Release`: POST `http://factory/arm/release` `{}`
7.  **Emergency Siren** (Type: Alarm)
    *   `Alert`: POST `http://factory/siren/alert` `{"level": "string"}`
    *   `Silence`: POST `http://factory/siren/silence` `{}`
8.  **Quality Camera** (Type: Camera)
    *   `Inspect`: POST `http://factory/cam/inspect` `{"mode": "string"}`
    *   `Zoom`: POST `http://factory/cam/zoom` `{"level": "float"}`

### Tasks
1.  **Emergency Shutdown**
    > "Immediately perform an emergency stop on the hydraulic press, stop the conveyor belt, trigger the emergency siren at 'critical' level, and flash the warning light red for 120 seconds."
2.  **Production Start**
    > "At 08:00, start the conveyor belt at speed 50, set the cooling fan to 1500 RPM, move the robotic arm to position (0, 10, 50), and turn the warning light to solid green."
3.  **Maintenance Cycle**
    > "At 14:00, stop the conveyor belt, silence the siren, calibrate the temp sensor, and move the robotic arm to position (0, 0, 0) for inspection."

---

## 3. Smart Hospital

### Devices
1.  **Patient Bed** (Type: Medical Bed)
    *   `Adjust Head`: POST `http://hospital/bed/head` `{"angle": "integer"}`
    *   `Adjust Feet`: POST `http://hospital/bed/feet` `{"angle": "integer"}`
    *   `Set Height`: POST `http://hospital/bed/height` `{"cm": "integer"}`
2.  **IV Drip** (Type: Medical Pump)
    *   `Set Rate`: POST `http://hospital/iv/set` `{"ml_per_hour": "float"}`
    *   `Stop`: POST `http://hospital/iv/stop` `{}`
    *   `Reset Alarm`: POST `http://hospital/iv/reset` `{}`
3.  **Room Lights** (Type: Light)
    *   `Turn On`: POST `http://hospital/lights/on` `{}`
    *   `Turn Off`: POST `http://hospital/lights/off` `{}`
    *   `Dim`: POST `http://hospital/lights/dim` `{"percentage": "integer"}`
4.  **Nurse Call** (Type: Alarm)
    *   `Alert`: POST `http://hospital/call/alert` `{"priority": "string"}`
    *   `Cancel`: POST `http://hospital/call/cancel` `{}`
5.  **Vital Monitor** (Type: Monitor)
    *   `Measure BP`: POST `http://hospital/monitor/bp` `{}`
    *   `Measure HR`: POST `http://hospital/monitor/hr` `{}`
    *   `Measure O2`: POST `http://hospital/monitor/o2` `{}`
6.  **HVAC** (Type: Climate)
    *   `Set Temp`: POST `http://hospital/hvac/set` `{"temp": "float"}`
    *   `Filter Mode`: POST `http://hospital/hvac/filter` `{"mode": "string (hepa/std)"}`
7.  **Door Access** (Type: Lock)
    *   `Lock`: POST `http://hospital/door/lock` `{}`
    *   `Unlock`: POST `http://hospital/door/unlock` `{"badge": "string"}`
    *   `Emergency Open`: POST `http://hospital/door/open` `{}`
8.  **Sanitizer Dispenser** (Type: Dispenser)
    *   `Dispense`: POST `http://hospital/sanitizer/dispense` `{"amount": "integer"}`
    *   `Check Level`: GET `http://hospital/sanitizer/level` `{}`

### Tasks
1.  **Night Rounds Prep**
    > "At 21:00, dim room lights to 20%, adjust bed head angle to 30 degrees, set IV drip rate to 40ml/hr, and lock the door."
2.  **Code Blue (Emergency)**
    > "Immediately turn on room lights to 100%, emergency open the door, set bed height to 50cm, and alert nurse call with 'critical' priority."
3.  **Morning Vitals**
    > "At 06:00, measure BP, measure HR, measure O2, and set HVAC temp to 23 degrees."

---

## 4. Smart Agriculture

### Devices
1.  **Sprinkler Valve A** (Type: Valve)
    *   `Open`: POST `http://farm/sprinkler/open` `{"duration": "integer"}`
    *   `Close`: POST `http://farm/sprinkler/close` `{}`
2.  **Soil Sensor** (Type: Sensor)
    *   `Read Moisture`: GET `http://farm/sensor/moisture` `{}`
    *   `Read pH`: GET `http://farm/sensor/ph` `{}`
    *   `Read Temp`: GET `http://farm/sensor/temp` `{}`
3.  **Greenhouse Roof** (Type: Motor)
    *   `Open`: POST `http://farm/roof/open` `{"percentage": "integer"}`
    *   `Close`: POST `http://farm/roof/close` `{}`
4.  **Fertilizer Pump** (Type: Pump)
    *   `Inject`: POST `http://farm/fert/inject` `{"liters": "float"}`
    *   `Mix`: POST `http://farm/fert/mix` `{"minutes": "integer"}`
    *   `Stop`: POST `http://farm/fert/stop` `{}`
5.  **Grow Lights** (Type: Light)
    *   `Turn On`: POST `http://farm/lights/on` `{}`
    *   `Turn Off`: POST `http://farm/lights/off` `{}`
    *   `Set Spectrum`: POST `http://farm/lights/spectrum` `{"type": "string (veg/bloom)"}`
6.  **Drone** (Type: UAV)
    *   `Patrol`: POST `http://farm/drone/patrol` `{"path_id": "string"}`
    *   `Spray`: POST `http://farm/drone/spray` `{"area_id": "string"}`
    *   `Return`: POST `http://farm/drone/home` `{}`
7.  **Weather Station** (Type: Sensor)
    *   `Read Rain`: GET `http://farm/weather/rain` `{}`
    *   `Read Wind`: GET `http://farm/weather/wind` `{}`
8.  **Heater** (Type: Heater)
    *   `Turn On`: POST `http://farm/heater/on` `{}`
    *   `Turn Off`: POST `http://farm/heater/off` `{}`
    *   `Set Temp`: POST `http://farm/heater/set` `{"temp": "float"}`

### Tasks
1.  **Morning Irrigation**
    > "At 05:00, open Sprinkler Valve A for 45 minutes, open greenhouse roof to 60%, and inject 3.5 liters of fertilizer."
2.  **Storm Protection**
    > "Close greenhouse roof, turn off grow lights, recall drone to home, and turn on heater to 20 degrees."
3.  **Harvest Prep**
    > "At 18:00, set grow lights spectrum to 'bloom', mix fertilizer for 20 minutes, and patrol with drone on path 'sector-4'."

---

## 5. Smart Retail

### Devices
1.  **Main Entrance** (Type: Door)
    *   `Unlock`: POST `http://store/door/unlock` `{}`
    *   `Lock`: POST `http://store/door/lock` `{}`
    *   `Auto Mode`: POST `http://store/door/auto` `{}`
2.  **Digital Signage** (Type: Display)
    *   `Set Content`: POST `http://store/sign/content` `{"id": "string"}`
    *   `Set Brightness`: POST `http://store/sign/bright` `{"level": "integer"}`
    *   `Schedule`: POST `http://store/sign/schedule` `{"playlist": "string"}`
3.  **HVAC** (Type: Climate)
    *   `Set Mode`: POST `http://store/hvac/mode` `{"mode": "string"}`
    *   `Set Temp`: POST `http://store/hvac/set` `{"temp": "float"}`
4.  **Security Grid** (Type: Alarm)
    *   `Arm`: POST `http://store/alarm/arm` `{"code": "string"}`
    *   `Disarm`: POST `http://store/alarm/disarm` `{"code": "string"}`
    *   `Bypass Zone`: POST `http://store/alarm/bypass` `{"zone": "integer"}`
5.  **POS Register** (Type: Computer)
    *   `Reboot`: POST `http://store/pos/reboot` `{}`
    *   `Update`: POST `http://store/pos/update` `{}`
    *   `Gen Report`: POST `http://store/pos/report` `{"type": "string"}`
6.  **Background Music** (Type: Audio)
    *   `Play`: POST `http://store/music/play` `{"genre": "string"}`
    *   `Set Volume`: POST `http://store/music/volume` `{"level": "integer"}`
7.  **Smart Shelf** (Type: Sensor)
    *   `Check Stock`: GET `http://store/shelf/stock` `{}`
    *   `Update Price`: POST `http://store/shelf/price` `{"amount": "float"}`
8.  **Fitting Room Light** (Type: Light)
    *   `Set Status`: POST `http://store/fitting/status` `{"state": "string (vacant/occupied)"}`
    *   `Cleaning Mode`: POST `http://store/fitting/clean` `{}`

### Tasks
1.  **Store Opening Routine**
    > "At 08:30, disarm security grid with code '1234', unlock main entrance, set HVAC to 'cool' mode at 21 degrees, and play 'Pop' music at volume 40."
2.  **Store Closing Routine**
    > "At 21:00, lock main entrance, arm security grid with code '9999', set HVAC to 'eco' mode, turn off digital signage, and generate daily POS report."
3.  **Mid-day Promo**
    > "At 12:00, set digital signage content to 'LUNCH_SPECIAL', set brightness to 100%, and update smart shelf price to 19.99."
