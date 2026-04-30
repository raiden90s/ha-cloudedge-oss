from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .camera import CloudEdgeCamera

DOMAIN = "cloudedge_oss"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    user_id = entry.data["user_id"]
    device_id = entry.data["device_id"]

    camera = CloudEdgeCamera(hass, user_id, device_id)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = camera

    await hass.config_entries.async_forward_entry_setups(entry, ["camera"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.entry_id in hass.data[DOMAIN]:
        del hass.data[DOMAIN][entry.entry_id]
    return await hass.config_entries.async_forward_entry_unload(entry, "camera")
