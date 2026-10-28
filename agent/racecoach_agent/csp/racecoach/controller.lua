--------
-- Kontroler pogody RaceCoach dla CSP WeatherFX.
-- Bazuje na domyślnym kontrolerze CSP (extension/weather-controllers/base): typ pogody, temperatury,
-- wiatr i stan toru pochodzą z ustawień sesji (race.ini). Deszcz, mokrość i stojącą wodę ustawia
-- agent RaceCoach przez pamięć współdzieloną; zmiany są płynne i potwierdzane.
--------

local CHANNEL = 'AcTools.CSP.Limited.RaceCoachWeather'
-- Układ musi odpowiadać agent/racecoach_agent/csp_weather.py (12 pól po 4 bajty).
local LAYOUT = [[
  int version; int requestId; float rain; float wetness; float water; float transition;
  int ackId; float appliedRain; float appliedWetness; float appliedWater; int heartbeat; int controllerVersion;
]]

local okChannel, channel = pcall(ac.writeMemoryMappedFile, CHANNEL, LAYOUT)
if not okChannel then
  ac.log('RaceCoach: brak kanału pogody: ' .. tostring(channel))
  channel = nil
end

local setConditions = ac.setConditionsSet2 or ac.setConditionsSet

local function clamp01(v)
  v = tonumber(v) or 0
  if v ~= v then return 0 end
  return math.max(0, math.min(1, v))
end

local function smooth(t)
  return t * t * (3 - 2 * t)
end

local function inputConditions()
  local result = ac.ConditionsSet()
  local weatherType = ac.getInputWeatherType()
  result.currentType = weatherType
  result.upcomingType = weatherType
  result.transition = 0
  result.variableA, result.variableB, result.variableC = 0, 0, 0
  result.temperatures = ac.getInputTemperatures()
  result.wind = ac.getInputWind()
  local okHumidity, humidity = pcall(ac.getInputHumidity, refbool(false))
  local okPressure, pressure = pcall(ac.getInputPressure, refbool(false))
  result.humidity = okHumidity and humidity or 0.5
  result.pressure = okPressure and pressure or 101325
  result.trackState = ac.getInputTrackState()
  return result, weatherType
end

local conditions, dryType = inputConditions()

local function typeForRain(rain)
  if rain < 0.01 then return dryType end
  if rain < 0.08 then return ac.WeatherType.LightDrizzle end
  if rain < 0.15 then return ac.WeatherType.Drizzle end
  if rain < 0.3 then return ac.WeatherType.LightRain end
  if rain < 0.55 then return ac.WeatherType.Rain end
  return ac.WeatherType.HeavyRain
end

local current = { rain = 0, wetness = 0, water = 0 }
local from = { rain = 0, wetness = 0, water = 0 }
local target = { rain = 0, wetness = 0, water = 0 }
local duration, elapsed = 0, 0
local lastRequest = nil

local function apply()
  local progress = duration > 0 and smooth(math.min(1, elapsed / duration)) or 1
  for _, key in ipairs({ 'rain', 'wetness', 'water' }) do
    current[key] = from[key] + (target[key] - from[key]) * progress
  end
  conditions.rainIntensity = current.rain
  conditions.rainWetness = current.wetness
  conditions.rainWater = current.water
  conditions.currentType = typeForRain(progress >= 1 and target.rain or from.rain)
  conditions.upcomingType = typeForRain(target.rain)
  conditions.transition = progress >= 1 and 0 or progress
  setConditions(conditions)
  if channel then
    channel.appliedRain = current.rain
    channel.appliedWetness = current.wetness
    channel.appliedWater = current.water
  end
end

local function readRequest(initial)
  lastRequest = channel.requestId
  for _, key in ipairs({ 'rain', 'wetness', 'water' }) do
    from[key] = current[key]
  end
  target = { rain = clamp01(channel.rain), wetness = clamp01(channel.wetness), water = clamp01(channel.water) }
  -- Warunki startowe obowiązują od pierwszej klatki; zmiany w trakcie jazdy narastają płynnie.
  duration = initial and 0 or math.max(0, tonumber(channel.transition) or 0)
  elapsed = 0
  channel.ackId = lastRequest
end

if channel then
  channel.controllerVersion = 1
  if channel.requestId ~= 0 then readRequest(true) end
end
apply()

local settled = true
function script.update(dt)
  if channel then
    channel.heartbeat = (channel.heartbeat + 1) % 2000000000
    channel.controllerVersion = 1
    if channel.requestId ~= 0 and channel.requestId ~= lastRequest then
      readRequest(lastRequest == nil)
      settled = false
    end
  end
  if not settled then
    elapsed = elapsed + dt
    apply()
    settled = duration <= 0 or elapsed >= duration
  end
end
