-- Equal sibling sizes with hy3. Source is pinned and built against this Hyprland.
local options = ...
if type(options) ~= "table" then options = {} end
local state_home = require("default.hypr.paths").state_home
-- Omarchy's bootstrap may still put the default state directory first.
-- Its saved-layout reader must resolve modules from the selected state home.
local state_template = state_home .. "/?.lua"
local search_paths = { state_template }
for template in package.path:gmatch("[^;]+") do
  if template ~= state_template then table.insert(search_paths, template) end
end
package.path = table.concat(search_paths, ";")

local plugin_path = options.plugin_path or os.getenv("HOME") .. "/.local/lib/omarchy-equal-tiling/libhy3-cosmic.so"
local signature = os.getenv("HYPRLAND_INSTANCE_SIGNATURE") or ""
local stamp = io.open(options.stamp_path or os.getenv("HOME") .. "/.local/lib/omarchy-equal-tiling/hyprland-commit", "r")
local commit = stamp and stamp:read("*l")
if stamp then stamp:close() end
if not commit or signature:sub(1, #commit + 1) ~= commit .. "_" then return end
-- Plugin declarations must be present on every reload, even when already loaded.
if not options.loaded then hl.plugin.load(plugin_path) end
if not hl.plugin.hy3 then return end
local hy3 = hl.plugin.hy3
if not hy3.move_cosmic then return end
hl.config({ general = { layout = "hy3" }, plugin = { hy3 = { group_inset = 0 } } })

local function active_hy3()
  local window = hl.get_active_window()
  return window and not window.floating and window.workspace
    and window.workspace.tiled_layout == "hy3"
end

-- hy3 keeps equal tiles equal as windows open, close, and move, so this module
-- does not rebalance and manual sizes stay. A config reload rebuilds the layout
-- with equal tiles. Super+Alt+P is the explicit way to change sizes.

-- Returns the tiled columns of a workspace, left to right, when it has exactly
-- three side by side and the active window is in the middle one. Rows of three
-- look the same, so each column keeps all of its windows.
-- Intentional: a pseudotiled window reports its own size, not its tile, and can
-- skew the result. The Lua API does not expose pseudotile state.
local function priority_columns(active)
  local columns, by_span = {}, {}
  for _, window in ipairs(hl.get_windows({workspace = active.workspace.id, floating = false})) do
    local span = window.at.x .. ":" .. window.size.x
    if not by_span[span] then
      by_span[span] = {x = window.at.x, width = window.size.x, windows = {}}
      table.insert(columns, by_span[span])
    end
    table.insert(by_span[span].windows, window)
    if window.address == active.address then by_span[span].active = true end
  end
  if #columns ~= 3 then return nil end
  table.sort(columns, function(a, b) return a.x < b.x end)
  for i = 2, 3 do
    if columns[i].x < columns[i - 1].x + columns[i - 1].width then return nil end
  end
  if columns[2].active then return columns end
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
      end
    else
      hl.dispatch(hl.dsp.window.move({direction = direction}))
    end
  end)
end
-- Arrangement is controlled entirely by Super+Shift+arrows.
hl.unbind("SUPER + J")
-- Sets the side columns to a quarter of the row each, so the middle gets half.
local function apply_priority(columns)
  local side = (columns[1].width + columns[2].width + columns[3].width) / 4
  -- hy3 rejects a resize that leaves the middle column without width.
  -- Shrinking the wider side first only gives the middle more, so both succeed.
  local sides = {columns[1], columns[3]}
  table.sort(sides, function(a, b) return a.width > b.width end)
  for _, column in ipairs(sides) do
    -- A stacked column moves on its first resize; the rest are no-ops.
    -- In rows of three, each row gets the same split.
    for _, window in ipairs(column.windows) do
      hl.dispatch(hl.dsp.window.resize({x = math.floor(side + 0.5), y = window.size.y, window = window}))
    end
  end
end

-- The middle of three columns takes half the width, like one 4K half of a
-- 7680 px ultrawide. The side columns share the rest. Press again, or press it
-- in any other layout, to make every tile on the workspace equal.
hl.unbind("SUPER + ALT + P")
o.bind("SUPER + ALT + P", "Toggle priority column / equal tiles", function()
  local active = hl.get_active_window()
  if not active_hy3() or active.fullscreen ~= 0 then return end
  local columns = priority_columns(active)
  if columns then
    local total = columns[1].width + columns[2].width + columns[3].width
    local tolerance = total / 100
    if math.abs(columns[1].width - total / 4) > tolerance or math.abs(columns[3].width - total / 4) > tolerance then
      apply_priority(columns)
      -- hy3 converts pixels to ratios against the width with gaps, so a large
      -- move lands a few pixels short. Window sizes report the final layout at
      -- once, even while animating, so a second pass corrects the rest.
      columns = priority_columns(active)
      if columns then apply_priority(columns) end
      return
    end
  end
  hl.dispatch(hy3.equalize({scope = "workspace"}))
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
end)

return true
