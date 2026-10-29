-- RaceCoach: sesja grupowa bez kolizji między autami (tryb ducha).
-- Skrypt online CSP, który AssettoServer przekazuje stanowiskom przez cfg/csp_extra_options.ini.
-- Wyłącza zderzenia z innymi autami (zostają kolizje z torem i barierami) i ponawia to co sekundę,
-- żeby objąć kierowców dołączających w trakcie sesji.

local function apply()
  local sim = ac.getSim()
  for i = 0, sim.carsCount - 1 do
    -- Te same argumenty co polecenie /noclip w AssettoServer: (indeks auta, wyłącz, zachowaj kolizje z torem).
    physics.disableCarCollisions(i, true, true)
  end
end

local timer = 0
apply()

function script.update(dt)
  timer = timer + dt
  if timer >= 1 then
    timer = 0
    apply()
  end
end
