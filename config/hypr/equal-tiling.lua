-- Equal sibling sizes with hy3. Source is pinned and built against this Hyprland.
local state_home = require("default.hypr.paths").state_home
-- Omarchy's bootstrap may still put the default state directory first.
-- Its saved-layout reader must resolve modules from the selected state home.
local state_template = state_home .. "/?.lua"
local search_paths = { state_template }
for template in package.path:gmatch("[^;]+") do
  if template ~= state_template then table.insert(search_paths, template) end
end
package.path = table.concat(search_paths, ";")

local plugin_path = os.getenv("HOME") .. "/.local/lib/omarchy-equal-tiling/libhy3-cosmic.so"
local signature = os.getenv("HYPRLAND_INSTANCE_SIGNATURE") or ""
local stamp = io.open(os.getenv("HOME") .. "/.local/lib/omarchy-equal-tiling/hyprland-commit", "r")
local commit = stamp and stamp:read("*l")
if stamp then stamp:close() end
if not commit or signature:sub(1, #commit + 1) ~= commit .. "_" then return end
-- Plugin declarations must be present on every reload, even when already loaded.
hl.plugin.load(plugin_path)
if not hl.plugin.hy3 then return end
local hy3 = hl.plugin.hy3
if not hy3.move_cosmic then return end
hl.config({ general = { layout = "hy3" }, plugin = { hy3 = { group_inset = 0 } } })

local function active_hy3()
  local window = hl.get_active_window()
  return window and not window.floating and window.workspace
    and window.workspace.tiled_layout == "hy3"
end
local function balance()
  local workspace = hl.get_active_workspace()
  if workspace and workspace.tiled_layout == "hy3" then
    hl.dispatch(hy3.equalize({scope = "workspace"}))
  end
end
local pending = false
local function balance_later()
  if pending then return end
  pending = true
  hl.timer(function()
    pending = false
    balance()
  end, {timeout = 60, type = "oneshot"})
end
for _, event in ipairs({"window.open", "window.close", "window.move_to_workspace", "workspace.active"}) do
  hl.on(event, balance_later)
end

for _, item in ipairs({{"LEFT", "l"}, {"RIGHT", "r"}, {"UP", "u"}, {"DOWN", "d"}}) do
  local key, direction = item[1], item[2]
  hl.unbind("SUPER + " .. key)
  o.bind("SUPER + " .. key, "Focus window " .. direction, function()
    if active_hy3() then hl.dispatch(hy3.move_focus(direction))
    else hl.dispatch(hl.dsp.focus({direction = direction})) end
  end)
  hl.unbind("SUPER + SHIFT + " .. key)
  local description = "Move window " .. key:lower() .. " through tiling groups"
  o.bind("SUPER + SHIFT + " .. key, description, function()
    if active_hy3() then
      local window = hl.get_active_window()
      if window and window.fullscreen == 0 then
        hl.dispatch(hy3.move_cosmic(direction))
        balance()
      end
    else
      hl.dispatch(hl.dsp.window.move({direction = direction}))
    end
  end)
end
-- Arrangement is controlled entirely by Super+Shift+arrows.
hl.unbind("SUPER + J")
-- Retiling changes the sibling count, so rebalance after Super+T too.
hl.unbind("SUPER + T")
o.bind("SUPER + T", "Toggle window floating/tiling", function()
  hl.dispatch(hl.dsp.window.float({action = "toggle"}))
  balance_later()
end)
-- Keep Omarchy's layout toggle useful with hy3 as the regular tiling layout.
hl.unbind("SUPER + L")
o.bind("SUPER + L", "Toggle equal tiling / scrolling", function()
  local workspace = hl.get_active_workspace()
  if not workspace then return end
  local layout = workspace.tiled_layout == "hy3" and "scrolling" or "hy3"
  local directory = state_home .. "/omarchy/workspace-layouts"
  -- A fresh home has no saved layouts yet. Quote the directory for the shell.
  os.execute("mkdir -p -- '" .. directory:gsub("'", "'\\''") .. "'")
  local path = directory .. "/" .. workspace.id .. ".lua"
  local file = io.open(path, "w")
  if file then
    local value = layout == "hy3" and '(hl.plugin.hy3 and "hy3" or "dwindle")' or '"scrolling"'
    file:write('hl.workspace_rule({workspace = "' .. workspace.id .. '", layout = ' .. value .. '})\n')
    file:close()
  end
  hl.workspace_rule({workspace = tostring(workspace.id), layout = layout})
  balance_later()
end)
