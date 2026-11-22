from odoo import models


class MirabilenetRegionScoped(models.AbstractModel):
    """Registros que cuelgan de una región.

    La regla de registro se evalúa antes de escribir: sin esta segunda
    comprobación, alguien podría mover un registro suyo a otra región.
    """
    _name = "mirabilenet.region.scoped"
    _description = "MIRABILENET: registro con región"
    _region_path = ("region_id",)

    def write(self, vals):
        result = super().write(vals)
        if set(vals) & set(self._region_path) and not self.env.su:
            self.flush_recordset()
            self.invalidate_recordset()
            self.check_access("write")
        return result
