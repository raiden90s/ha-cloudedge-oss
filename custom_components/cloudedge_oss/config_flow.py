import voluptuous as vol
from homeassistant import config_entries

DOMAIN = "cloudedge_oss"

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Salva i dati e crea l'integrazione
            return self.async_create_entry(title="CloudEdge Campanello", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("user_id"): int,
                vol.Required("device_id"): int,
            }),
            errors=errors,
        )
